from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

DEFAULT_JOB_TTL_SECONDS = 60 * 60
DEFAULT_MAX_RETAINED_JOBS = 40
DEFAULT_MAX_RUNNING_JOBS = 4
DEFAULT_RECENT_LOG_LIMIT = 25

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
ACTIVE_STATUSES = {"queued", "running", "cancelling"}


class JobCancelledError(Exception):
    """Raised when a background job cooperatively stops after cancellation."""


class CancelToken:
    """Thread-safe cancellation token passed to cancellable background jobs."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation."""
        self._event.set()

    @property
    def cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._event.is_set()

    def check(self) -> None:
        """Raise when cancellation has been requested."""
        if self.cancelled:
            raise JobCancelledError("job cancelled")


@dataclass
class BackgroundJob:
    """State for one queued operation started from the web UI."""

    job_id: str
    kind: str
    title: str
    problem_id: str
    status: str = "queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_supported: bool = False
    cancel_requested: bool = False
    cancel_mode: str = "cooperative"
    cancel_blocked_reason: str | None = None
    cancelled_at: datetime | None = None
    app: str | None = None
    lane: str | None = None
    target: dict[str, Any] = field(default_factory=dict)
    progress: dict[str, Any] = field(default_factory=dict)
    last_log: str = ""
    logs: list[dict[str, Any]] = field(default_factory=list)
    result_actions: dict[str, Any] = field(default_factory=dict)
    input_snapshot_summary: str | None = None
    queued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def expires_at(self, ttl_seconds: int) -> datetime | None:
        """Return when a completed job becomes stale."""
        if self.status not in TERMINAL_STATUSES:
            return None
        return self.updated_at + timedelta(seconds=ttl_seconds)

    def stale(self, ttl_seconds: int, now: datetime | None = None) -> bool:
        """Return whether this completed job is past its visible freshness window."""
        expires_at = self.expires_at(ttl_seconds)
        if expires_at is None:
            return False
        return (now or datetime.now(UTC)) >= expires_at

    def to_dict(
        self,
        *,
        ttl_seconds: int = DEFAULT_JOB_TTL_SECONDS,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Return a JSON-friendly representation of this job."""
        is_stale = self.stale(ttl_seconds, now)
        expires_at = self.expires_at(ttl_seconds)
        return {
            "jobId": self.job_id,
            "kind": self.kind,
            "title": self.title,
            "problemId": self.problem_id,
            "status": "stale" if is_stale else self.status,
            "previousStatus": self.status if is_stale else None,
            "stale": is_stale,
            "result": self.result,
            "error": self.error,
            "cancelSupported": self.cancel_supported,
            "cancelRequested": self.cancel_requested,
            "cancelMode": self.cancel_mode,
            "cancelBlockedReason": self.cancel_blocked_reason,
            "cancelledAt": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "app": self.app,
            "lane": self.lane,
            "target": self.target,
            "progress": self.progress,
            "lastLog": self.last_log,
            "logs": self.logs,
            "resultActions": self.result_actions,
            "inputSnapshotSummary": self.input_snapshot_summary,
            "queuedAt": self.queued_at.isoformat(),
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "finishedAt": self.finished_at.isoformat() if self.finished_at else None,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "expiresAt": expires_at.isoformat() if expires_at is not None else None,
        }


@dataclass(frozen=True)
class _QueuedOperation:
    operation: Callable[..., dict[str, Any]]
    cancel_supported: bool


class BackgroundJobStore:
    """Thread-safe in-memory queue for local web background jobs."""

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_JOB_TTL_SECONDS,
        max_jobs: int = DEFAULT_MAX_RETAINED_JOBS,
        max_running_jobs: int = DEFAULT_MAX_RUNNING_JOBS,
        lane_limits: dict[str, int] | None = None,
        recent_log_limit: int = DEFAULT_RECENT_LOG_LIMIT,
    ) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, BackgroundJob] = {}
        self._tokens: dict[str, CancelToken] = {}
        self._operations: dict[str, _QueuedOperation] = {}
        self.ttl_seconds = ttl_seconds
        self.max_jobs = max_jobs
        self.max_running_jobs = max_running_jobs
        self.lane_limits = lane_limits or {}
        self.recent_log_limit = recent_log_limit

    def start(
        self,
        *,
        kind: str,
        title: str,
        problem_id: str,
        operation: Callable[..., dict[str, Any]],
        cancel_supported: bool = False,
        app: str | None = None,
        lane: str | None = None,
        target: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
        result_actions: dict[str, Any] | None = None,
        input_snapshot_summary: str | None = None,
        cancel_mode: str = "cooperative",
        cancel_blocked_reason: str | None = None,
    ) -> BackgroundJob:
        """Enqueue an operation and return its job state."""
        job = BackgroundJob(
            job_id=uuid.uuid4().hex,
            kind=kind,
            title=title,
            problem_id=problem_id,
            cancel_supported=cancel_supported,
            app=app,
            lane=lane,
            target=target or {},
            progress=progress or {},
            result_actions=result_actions or {},
            input_snapshot_summary=input_snapshot_summary,
            cancel_mode=cancel_mode,
            cancel_blocked_reason=cancel_blocked_reason,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._operations[job.job_id] = _QueuedOperation(operation, cancel_supported)
            self._prune_locked()
        self._spawn_ready_jobs()
        return job

    def running_count(self) -> int:
        """Return the number of currently running retained jobs."""
        with self._lock:
            return self.running_count_locked()

    def running_count_locked(self) -> int:
        """Return the number of running jobs while the caller holds the lock."""
        return sum(1 for job in self._jobs.values() if job.status in {"running", "cancelling"})

    def queued_count(self) -> int:
        """Return the number of queued jobs."""
        with self._lock:
            return sum(1 for job in self._jobs.values() if job.status == "queued")

    def get(self, job_id: str) -> BackgroundJob | None:
        """Return a job by id if it is still retained."""
        with self._lock:
            self._prune_locked()
            return self._jobs.get(job_id)

    def list(self, problem_id: str | None = None) -> list[BackgroundJob]:
        """Return retained jobs, active first and then newest first."""
        with self._lock:
            self._prune_locked()
            jobs = [
                job
                for job in self._jobs.values()
                if problem_id is None or job.problem_id == problem_id
            ]
        return sorted(jobs, key=self._sort_key)

    def dismiss(self, job_id: str) -> bool:
        """Remove a retained job by id."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in ACTIVE_STATUSES:
                return False
            self._tokens.pop(job_id, None)
            self._operations.pop(job_id, None)
            self._jobs.pop(job_id, None)
            return True

    def clear_completed(self, predicate: Callable[[BackgroundJob], bool] | None = None) -> int:
        """Remove terminal retained jobs and return the number removed."""
        with self._lock:
            removable = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in TERMINAL_STATUSES and (predicate is None or predicate(job))
            ]
            for job_id in removable:
                self._tokens.pop(job_id, None)
                self._operations.pop(job_id, None)
                self._jobs.pop(job_id, None)
            return len(removable)

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued job or request cancellation for a running job."""
        start_after: list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]] = []
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            now = datetime.now(UTC)
            if job.status == "queued":
                job.status = "cancelled"
                job.cancel_requested = True
                job.cancelled_at = now
                job.finished_at = now
                job.updated_at = now
                self._operations.pop(job_id, None)
                self._tokens.pop(job_id, None)
                start_after = self._ready_jobs_locked()
            elif job.status == "running" and job.cancel_supported:
                token = self._tokens.get(job_id)
                if token is None:
                    return False
                job.status = "cancelling"
                job.cancel_requested = True
                job.cancelled_at = now
                job.updated_at = now
                self._append_log_locked(job, "Cancel requested.")
                token.cancel()
            else:
                return False
        self._spawn_jobs(start_after)
        return True

    def update_progress(
        self,
        job_id: str,
        message: str | None = None,
        *,
        current: int | None = None,
        total: int | None = None,
        label: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Update one job's latest progress and recent logs."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            progress = dict(job.progress or {})
            if current is not None:
                progress["current"] = current
            if total is not None:
                progress["total"] = total
            if label is not None:
                progress["label"] = label
            if extra:
                progress.update(extra)
            if message:
                progress["message"] = message
                job.last_log = message
                self._append_log_locked(job, message)
            job.progress = progress
            job.updated_at = datetime.now(UTC)

    def job_dict(self, job: BackgroundJob) -> dict[str, Any]:
        """Return a JSON-friendly job dictionary using this store's policy."""
        return job.to_dict(ttl_seconds=self.ttl_seconds)

    def _finish(
        self,
        job_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            now = datetime.now(UTC)
            job.status = status
            job.result = result
            job.error = error
            job.finished_at = now
            job.updated_at = now
            if status == "cancelled":
                job.cancel_requested = True
                job.cancelled_at = job.cancelled_at or now
            if status == "failed" and error:
                self._append_log_locked(job, error)
            self._tokens.pop(job_id, None)
            self._operations.pop(job_id, None)
            self._prune_locked()
            starts = self._ready_jobs_locked()
        self._spawn_jobs(starts)

    def _ready_jobs_locked(
        self,
    ) -> list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]]:
        starts: list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]] = []
        while self.running_count_locked() + len(starts) < self.max_running_jobs:
            candidate = self._next_ready_job_locked(starts)
            if candidate is None:
                break
            operation = self._operations.get(candidate.job_id)
            if operation is None:
                candidate.status = "cancelled"
                candidate.cancel_requested = True
                candidate.cancelled_at = datetime.now(UTC)
                candidate.finished_at = candidate.cancelled_at
                candidate.updated_at = candidate.cancelled_at
                continue
            token = CancelToken() if operation.cancel_supported else None
            if token is not None:
                self._tokens[candidate.job_id] = token
            now = datetime.now(UTC)
            candidate.status = "running"
            candidate.started_at = now
            candidate.updated_at = now
            starts.append((candidate, token, operation))
        return starts

    def _next_ready_job_locked(
        self, planned: list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]]
    ) -> BackgroundJob | None:
        queued = sorted(
            (job for job in self._jobs.values() if job.status == "queued"),
            key=lambda job: job.queued_at,
        )
        planned_lanes: dict[str, int] = {}
        for job, _token, _operation in planned:
            if job.lane:
                planned_lanes[job.lane] = planned_lanes.get(job.lane, 0) + 1
        for job in queued:
            if not job.lane:
                return job
            lane_limit = self.lane_limits.get(job.lane, 1)
            running_in_lane = sum(
                1
                for item in self._jobs.values()
                if item.lane == job.lane and item.status in {"running", "cancelling"}
            )
            if running_in_lane + planned_lanes.get(job.lane, 0) < lane_limit:
                return job
        return None

    def _spawn_ready_jobs(self) -> None:
        with self._lock:
            starts = self._ready_jobs_locked()
        self._spawn_jobs(starts)

    def _spawn_jobs(
        self, starts: list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]]
    ) -> None:
        for job, token, operation in starts:
            threading.Thread(
                target=self._run_operation,
                args=(job.job_id, token, operation),
                daemon=True,
            ).start()

    def _run_operation(
        self,
        job_id: str,
        token: CancelToken | None,
        operation: _QueuedOperation,
    ) -> None:
        try:
            if operation.cancel_supported:
                result = operation.operation(token)
                if token is not None and token.cancelled:
                    self._finish(job_id, "cancelled")
                else:
                    self._finish(job_id, "succeeded", result=result)
            else:
                self._finish(job_id, "succeeded", result=operation.operation())
        except JobCancelledError:
            self._finish(job_id, "cancelled")
        except Exception as exc:  # noqa: BLE001 - job errors are shown to the user.
            self._finish(job_id, "failed", error=str(exc))

    def _append_log_locked(self, job: BackgroundJob, message: str) -> None:
        job.last_log = message
        job.logs.append(
            {
                "message": message,
                "createdAt": datetime.now(UTC).isoformat(),
            }
        )
        if len(job.logs) > self.recent_log_limit:
            del job.logs[: len(job.logs) - self.recent_log_limit]

    def _prune_locked(self) -> None:
        """Keep active jobs and the newest completed jobs within the retention limit."""
        if self.max_jobs <= 0:
            return
        if len(self._jobs) <= self.max_jobs:
            return
        completed = sorted(
            (job for job in self._jobs.values() if job.status in TERMINAL_STATUSES),
            key=lambda job: job.updated_at,
        )
        while len(self._jobs) > self.max_jobs and completed:
            oldest = completed.pop(0)
            self._jobs.pop(oldest.job_id, None)
            self._tokens.pop(oldest.job_id, None)
            self._operations.pop(oldest.job_id, None)

    @staticmethod
    def _sort_key(job: BackgroundJob) -> tuple[int, datetime]:
        if job.status in {"running", "cancelling"}:
            return (0, job.started_at or job.queued_at)
        if job.status == "queued":
            return (1, job.queued_at)
        return (2, datetime.max.replace(tzinfo=UTC) - (job.finished_at or job.updated_at))


__all__ = [
    "ACTIVE_STATUSES",
    "BackgroundJob",
    "BackgroundJobStore",
    "CancelToken",
    "DEFAULT_JOB_TTL_SECONDS",
    "DEFAULT_MAX_RETAINED_JOBS",
    "DEFAULT_MAX_RUNNING_JOBS",
    "JobCancelledError",
    "TERMINAL_STATUSES",
]
