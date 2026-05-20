from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class BackgroundJob:
    """State for one background operation started from the web UI."""

    job_id: str
    kind: str
    title: str
    problem_id: str
    status: str = "running"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation of this job."""
        return {
            "jobId": self.job_id,
            "kind": self.kind,
            "title": self.title,
            "problemId": self.problem_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }


class BackgroundJobStore:
    """Thread-safe in-memory store for local web background jobs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, BackgroundJob] = {}

    def start(
        self,
        *,
        kind: str,
        title: str,
        problem_id: str,
        operation: Callable[[], dict[str, Any]],
    ) -> BackgroundJob:
        """Start an operation in a daemon thread and return its job state."""
        job = BackgroundJob(
            job_id=uuid.uuid4().hex,
            kind=kind,
            title=title,
            problem_id=problem_id,
        )
        with self._lock:
            self._jobs[job.job_id] = job

        def worker() -> None:
            try:
                result = operation()
                self._finish(job.job_id, "succeeded", result=result)
            except Exception as exc:  # noqa: BLE001 - job errors are shown to the user.
                self._finish(job.job_id, "failed", error=str(exc))

        threading.Thread(target=worker, daemon=True).start()
        return job

    def get(self, job_id: str) -> BackgroundJob | None:
        """Return a job by id if it is still retained."""
        with self._lock:
            return self._jobs.get(job_id)

    def _finish(
        self,
        job_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            job.result = result
            job.error = error
            job.updated_at = datetime.now(UTC)
