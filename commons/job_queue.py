"""웹 API에서 사용하는 백그라운드 작업의 상태, 취소 토큰, 실행 큐, 보존 정책을 관리하는 공통 모듈입니다."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from commons.job_persistence import AtomicJsonFile

DEFAULT_JOB_TTL_SECONDS = 60 * 60
DEFAULT_MAX_RETAINED_JOBS = 40
DEFAULT_MAX_RUNNING_JOBS = 4
DEFAULT_RECENT_LOG_LIMIT = 25
JOB_HISTORY_SCHEMA_VERSION = 1
INTERRUPTED_JOB_MESSAGE = (
    "애플리케이션이 재시작되어 작업이 중단되었습니다. 안전을 위해 자동 재개하지 않았습니다."
)

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
ACTIVE_STATUSES = {"queued", "running", "cancelling"}
STAGE_KEYWORDS = [
    ("cases", ("cases.yml", "cases", "case compilation", "cases 검사")),
    ("tools", ("tool", "compile", "compiling", "도구", "컴파일")),
    ("validation", ("validation", "validating", "generated data", "데이터", "벨리데이션")),
    ("solutions", ("solution", "expected", "verifying", "솔루션", "기대 결과")),
    ("pack", ("pack", ".aljpack", "팩", "빌드")),
]
STAGE_LABELS = {
    "cases": "cases.yml 검사",
    "tools": "도구 컴파일",
    "validation": "데이터 생성+검증",
    "solutions": "솔루션 기대 결과",
    "pack": "팩 생성",
    "unknown": "검증",
}


class JobCancelledError(Exception):
    """협력적 취소가 요청된 작업 실행을 중단하기 위해 작업 함수 안에서 발생시키는 예외입니다."""


def infer_failure_stage(*values: Any) -> str:
    """작업 종류, 단계 라벨, 메시지에서 공통 실패 단계 키를 추론합니다."""
    text = " ".join(str(value or "") for value in values).lower()
    for stage, keywords in STAGE_KEYWORDS:
        if any(keyword.lower() in text for keyword in keywords):
            return stage
    return "unknown"


def stage_label(stage: str | None) -> str:
    return STAGE_LABELS.get(stage or "unknown", STAGE_LABELS["unknown"])


class CancelToken:
    """실행 중인 작업에 취소 요청을 전달하고 작업 함수가 중단 여부를 확인할 수 있게 하는 토큰입니다."""

    def __init__(self) -> None:
        """취소 요청 여부를 스레드 사이에서 공유할 이벤트 객체로 초기화합니다."""
        self._event = threading.Event()

    def cancel(self) -> None:
        """대기 중인 작업은 즉시 취소 처리하고, 실행 중인 취소 가능 작업에는 취소 토큰을 전달합니다.

        Args:
            job_id (str): 취소할 백그라운드 작업 식별자입니다.

        Returns:
            bool: 취소 요청이 받아들여졌으면 `True`, 대상이 없거나 취소할 수 없으면 `False`입니다.
        """
        self._event.set()

    @property
    def cancelled(self) -> bool:
        """현재 토큰에 취소 요청이 들어왔는지 확인합니다.

        Returns:
            bool: 취소 요청이 기록되어 있으면 `True`, 아니면 `False`입니다.
        """
        return self._event.is_set()

    def check(self) -> None:
        """취소 요청이 기록된 경우 작업 실행을 중단하도록 `JobCancelledError`를 발생시킵니다."""
        if self.cancelled:
            raise JobCancelledError("job cancelled")


@dataclass
class BackgroundJob:
    """큐에 등록된 백그라운드 작업의 식별자, 상태, 진행률, 로그, 결과, 취소 정보를 보관하는 데이터 객체입니다."""

    job_id: str
    kind: str
    title: str
    problem_id: str
    status: str = "queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    outcome: str | None = None
    failure_stage: str | None = None
    failure_stage_label: str | None = None
    failure_details: list[dict[str, Any]] = field(default_factory=list)
    error_kind: str | None = None
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
        """완료된 작업이 TTL 정책에 따라 오래된 작업으로 바뀌는 시각을 계산합니다.

        Args:
            ttl_seconds (int): 완료 작업을 최신 상태로 유지할 초 단위 기간입니다.

        Returns:
            datetime | None: 터미널 상태 작업의 만료 시각입니다. 아직 실행 중이면 `None`입니다.
        """
        if self.status not in TERMINAL_STATUSES:
            return None
        return self.updated_at + timedelta(seconds=ttl_seconds)

    def stale(self, ttl_seconds: int, now: datetime | None = None) -> bool:
        """완료된 작업이 TTL을 지나 오래된 상태로 표시되어야 하는지 판정합니다.

        Args:
            ttl_seconds (int): 완료 작업을 최신 상태로 유지할 초 단위 기간입니다.
            now (datetime | None): 비교 기준 시각입니다. 생략하면 현재 UTC 시각을 사용합니다.

        Returns:
            bool: 작업이 만료 시각을 지났으면 `True`, 아니면 `False`입니다.
        """
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
        """프런트엔드와 API 응답에서 사용하는 camelCase 작업 상태 사전으로 변환합니다.

        Args:
            ttl_seconds (int): stale 상태 계산에 사용할 완료 작업 보존 기간입니다.
            now (datetime | None): stale 상태 계산 기준 시각입니다.

        Returns:
            dict[str, Any]: 작업 상태, 결과, 취소 정보, 진행률, 로그, 타임스탬프를 담은 응답 사전입니다.
        """
        is_stale = self.stale(ttl_seconds, now)
        expires_at = self.expires_at(ttl_seconds)
        status = "stale" if is_stale else self.status
        outcome = self._effective_outcome(status)
        return {
            "jobId": self.job_id,
            "kind": self.kind,
            "title": self.title,
            "problemId": self.problem_id,
            "status": status,
            "previousStatus": self.status if is_stale else None,
            "stale": is_stale,
            "result": self.result,
            "error": self.error,
            "outcome": outcome,
            "failureStage": self.failure_stage,
            "failureStageLabel": self.failure_stage_label,
            "failureDetails": self.failure_details,
            "errorKind": self.error_kind,
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

    def _effective_outcome(self, status: str) -> str:
        """작업 실행 상태와 별개로 사용자가 봐야 하는 결과 상태를 계산합니다."""
        if status == "stale":
            return "stale"
        if status in ACTIVE_STATUSES:
            return "pending"
        if status == "cancelled":
            return "cancelled"
        if self.outcome:
            return self.outcome
        if status == "failed":
            return "failed"
        if status == "succeeded":
            return "passed"
        return status

    def to_storage_dict(self) -> dict[str, Any]:
        """재시작 복원을 위해 내부 필드 이름을 유지한 JSON 직렬화 가능 사전을 만듭니다."""
        return {item.name: getattr(self, item.name) for item in dataclass_fields(self)}

    @classmethod
    def from_storage_dict(cls, payload: dict[str, Any]) -> BackgroundJob:
        """저장된 내부 상태 사전에서 작업 객체를 복원합니다."""
        if not isinstance(payload, dict):
            raise ValueError("stored job must be an object")
        field_names = {item.name for item in dataclass_fields(cls)}
        values = {name: value for name, value in payload.items() if name in field_names}
        for required in ("job_id", "kind", "title", "problem_id"):
            if not isinstance(values.get(required), str) or not values[required]:
                raise ValueError(f"stored job has invalid {required}")
        status = values.get("status", "queued")
        if status not in ACTIVE_STATUSES | TERMINAL_STATUSES:
            raise ValueError(f"stored job has invalid status: {status}")
        for name in ("progress", "result_actions", "target"):
            if name in values and not isinstance(values[name], dict):
                raise ValueError(f"stored job has invalid {name}")
        for name in ("failure_details", "logs"):
            if name in values and not isinstance(values[name], list):
                raise ValueError(f"stored job has invalid {name}")
        if values.get("result") is not None and not isinstance(values["result"], dict):
            raise ValueError("stored job has invalid result")
        for name in (
            "cancelled_at",
            "queued_at",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ):
            if name not in values or values[name] is None:
                continue
            parsed = datetime.fromisoformat(str(values[name]).replace("Z", "+00:00"))
            values[name] = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        return cls(**values)


@dataclass(frozen=True)
class _QueuedOperation:
    """작업 큐에 보관된 실행 함수와 취소 지원 여부를 함께 담는 내부 값 객체입니다."""

    operation: Callable[..., dict[str, Any]]
    cancel_supported: bool
    terminal_callback: Callable[[BackgroundJob], None] | None = None


class BackgroundJobStore:
    """백그라운드 작업을 등록, 실행, 취소, 조회하고 동시 실행 수와 보존 개수를 제한하는 스레드 안전 저장소입니다."""

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_JOB_TTL_SECONDS,
        max_jobs: int = DEFAULT_MAX_RETAINED_JOBS,
        max_running_jobs: int = DEFAULT_MAX_RUNNING_JOBS,
        lane_limits: dict[str, int] | None = None,
        recent_log_limit: int = DEFAULT_RECENT_LOG_LIMIT,
        persistence_path: Path | str | None = None,
    ) -> None:
        """작업 저장소의 보존 기간, 동시 실행 한도, 레인별 제한, 최근 로그 개수를 설정합니다.

        Args:
            ttl_seconds (int): 완료된 작업을 최신 상태로 유지할 초 단위 기간입니다.
            max_jobs (int): 저장소에 보존할 최대 작업 수입니다.
            max_running_jobs (int): 동시에 실행할 수 있는 전체 작업 수입니다.
            lane_limits (dict[str, int] | None): 레인 이름별 동시 실행 제한입니다.
            recent_log_limit (int): 작업마다 보존할 최근 로그 항목 수입니다.
            persistence_path (Path | str | None): 재시작 복원용 atomic JSON 파일 경로입니다.
        """
        self._lock = threading.Lock()
        self._jobs: dict[str, BackgroundJob] = {}
        self._tokens: dict[str, CancelToken] = {}
        self._operations: dict[str, _QueuedOperation] = {}
        self.ttl_seconds = ttl_seconds
        self.max_jobs = max_jobs
        self.max_running_jobs = max_running_jobs
        self.lane_limits = lane_limits or {}
        self.recent_log_limit = recent_log_limit
        self._history = AtomicJsonFile(persistence_path) if persistence_path is not None else None
        self._load_history()

    @property
    def persistence_path(self) -> Path | None:
        """설정된 영속 작업 이력 파일 경로를 반환합니다."""
        return self._history.path if self._history is not None else None

    @property
    def persistence_error(self) -> str | None:
        """최근 작업 이력 읽기 또는 쓰기 오류를 반환합니다."""
        return self._history.last_error if self._history is not None else None

    def _load_history(self) -> None:
        if self._history is None:
            return
        payload = self._history.read()
        if payload is None:
            return
        try:
            if not isinstance(payload, dict):
                raise ValueError("job history root must be an object")
            if payload.get("schemaVersion") != JOB_HISTORY_SCHEMA_VERSION:
                raise ValueError("unsupported job history schema")
            stored_jobs = payload.get("jobs")
            if not isinstance(stored_jobs, list):
                raise ValueError("job history jobs must be an array")
            jobs = [BackgroundJob.from_storage_dict(item) for item in stored_jobs]
            if len({job.job_id for job in jobs}) != len(jobs):
                raise ValueError("job history contains duplicate job ids")
        except (TypeError, ValueError) as exc:
            self._history.quarantine(f"invalid job history: {exc}")
            return

        changed = False
        now = datetime.now(UTC)
        with self._lock:
            self._jobs = {job.job_id: job for job in jobs}
            for job in self._jobs.values():
                if job.status not in ACTIVE_STATUSES:
                    continue
                changed = True
                previous_status = job.status
                job.status = "failed"
                job.error = INTERRUPTED_JOB_MESSAGE
                job.outcome = "failed"
                job.error_kind = "interrupted"
                job.failure_stage = "interrupted"
                job.failure_stage_label = "재시작으로 중단"
                job.failure_details = [
                    {
                        "type": "interrupted",
                        "label": "재시작으로 중단",
                        "target": self._target_label(job),
                        "message": INTERRUPTED_JOB_MESSAGE,
                        "previousStatus": previous_status,
                    }
                ]
                job.finished_at = now
                job.updated_at = now
                self._append_log_locked(job, INTERRUPTED_JOB_MESSAGE)
            changed = self._prune_locked() or changed
            if changed:
                self._persist_locked()

    def _persist_locked(self) -> None:
        """현재 락 안의 작업 스냅샷을 영속 파일에 기록합니다."""
        if self._history is None:
            return
        jobs = sorted(self._jobs.values(), key=lambda job: (job.created_at, job.job_id))
        self._history.write(
            {
                "schemaVersion": JOB_HISTORY_SCHEMA_VERSION,
                "savedAt": datetime.now(UTC),
                "jobs": [job.to_storage_dict() for job in jobs],
            }
        )

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
        terminal_callback: Callable[[BackgroundJob], None] | None = None,
    ) -> BackgroundJob:
        """새 백그라운드 작업을 큐에 등록하고 실행 가능한 작업이 있으면 즉시 스레드로 시작합니다.

        Args:
            kind (str): 화면과 API에서 작업을 구분할 작업 종류입니다.
            title (str): 작업 목록에 표시할 사용자용 제목입니다.
            problem_id (str): 작업이 속한 문제 식별자입니다. 작업공간 단위 작업은 공용 식별자를 사용할 수 있습니다.
            operation (Callable[..., dict[str, Any]]): 백그라운드 스레드에서 실행할 작업 함수입니다.
            cancel_supported (bool): 작업 함수가 취소 토큰을 받아 협력적으로 중단할 수 있는지 여부입니다.
            app (str | None): 작업을 생성한 애플리케이션 또는 화면 영역 이름입니다.
            lane (str | None): 동시 실행 제한을 별도로 적용할 작업 레인 이름입니다.
            target (dict[str, Any] | None): 작업 대상 문제, 파일, 패키지 등 UI가 표시할 메타데이터입니다.
            progress (dict[str, Any] | None): 작업 시작 시 노출할 초기 진행 상태입니다.
            result_actions (dict[str, Any] | None): 완료 후 UI가 제공할 다운로드나 이동 동작 정보입니다.
            input_snapshot_summary (str | None): 작업 시작 시점의 입력 상태를 설명하는 요약 문자열입니다.
            cancel_mode (str): 취소 방식 표시 값입니다. 협력적 취소와 취소 불가 작업 구분에 사용합니다.
            cancel_blocked_reason (str | None): 취소할 수 없는 작업일 때 UI에 표시할 사유입니다.

        Returns:
            BackgroundJob: 큐에 등록된 작업 상태 객체입니다.
        """
        job = self._new_job(
            kind=kind,
            title=title,
            problem_id=problem_id,
            cancel_supported=cancel_supported,
            app=app,
            lane=lane,
            target=target,
            progress=progress,
            result_actions=result_actions,
            input_snapshot_summary=input_snapshot_summary,
            cancel_mode=cancel_mode,
            cancel_blocked_reason=cancel_blocked_reason,
        )
        return self._register_job(job, operation, cancel_supported, terminal_callback)

    def start_with_progress(
        self,
        *,
        kind: str,
        title: str,
        problem_id: str,
        operation: Callable[[CancelToken, Callable[..., None]], dict[str, Any]],
        cancel_supported: bool = True,
        app: str | None = None,
        lane: str | None = None,
        target: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
        result_actions: dict[str, Any] | None = None,
        input_snapshot_summary: str | None = None,
        cancel_mode: str = "cooperative",
        cancel_blocked_reason: str | None = None,
        terminal_callback: Callable[[BackgroundJob], None] | None = None,
    ) -> BackgroundJob:
        """job id가 확정된 뒤 progress callback을 구성해 취소 가능한 작업을 시작합니다."""
        job = self._new_job(
            kind=kind,
            title=title,
            problem_id=problem_id,
            cancel_supported=cancel_supported,
            app=app,
            lane=lane,
            target=target,
            progress=progress,
            result_actions=result_actions,
            input_snapshot_summary=input_snapshot_summary,
            cancel_mode=cancel_mode,
            cancel_blocked_reason=cancel_blocked_reason,
        )

        def run(cancel_token: CancelToken | None = None) -> dict[str, Any]:
            token = cancel_token or CancelToken()

            def progress_callback(
                message: str,
                current: int | None = None,
                total: int | None = None,
                label: str | None = None,
                **extra,
            ) -> None:
                token.check()
                self.update_progress(
                    job.job_id,
                    message,
                    current=current,
                    total=total,
                    label=label,
                    extra=extra or None,
                )

            return operation(token, progress_callback)

        return self._register_job(job, run, cancel_supported, terminal_callback)

    def _new_job(
        self,
        *,
        kind: str,
        title: str,
        problem_id: str,
        cancel_supported: bool,
        app: str | None,
        lane: str | None,
        target: dict[str, Any] | None,
        progress: dict[str, Any] | None,
        result_actions: dict[str, Any] | None,
        input_snapshot_summary: str | None,
        cancel_mode: str,
        cancel_blocked_reason: str | None,
    ) -> BackgroundJob:
        return BackgroundJob(
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

    def _register_job(
        self,
        job: BackgroundJob,
        operation: Callable[..., dict[str, Any]],
        cancel_supported: bool,
        terminal_callback: Callable[[BackgroundJob], None] | None = None,
    ) -> BackgroundJob:
        with self._lock:
            self._jobs[job.job_id] = job
            self._operations[job.job_id] = _QueuedOperation(
                operation, cancel_supported, terminal_callback
            )
            self._prune_locked()
            self._persist_locked()
        self._spawn_ready_jobs()
        return job

    def running_count(self) -> int:
        """현재 실행 중이거나 취소 중인 작업 수를 스레드 안전하게 계산합니다.

        Returns:
            int: 실행 슬롯을 점유 중인 작업 수입니다.
        """
        with self._lock:
            return self.running_count_locked()

    def running_count_locked(self) -> int:
        """이미 락을 잡은 코드 경로에서 실행 슬롯을 점유 중인 작업 수를 계산합니다.

        Returns:
            int: 실행 중 또는 취소 중 상태의 작업 수입니다.
        """
        return sum(1 for job in self._jobs.values() if job.status in {"running", "cancelling"})

    def queued_count(self) -> int:
        """아직 시작되지 않고 큐에 대기 중인 작업 수를 계산합니다.

        Returns:
            int: `queued` 상태 작업 수입니다.
        """
        with self._lock:
            return sum(1 for job in self._jobs.values() if job.status == "queued")

    def get(self, job_id: str) -> BackgroundJob | None:
        """작업 식별자로 현재 저장소에 남아 있는 작업을 조회합니다. 조회 전에 만료된 완료 작업을 정리합니다.

        Args:
            job_id (str): 조회할 백그라운드 작업 식별자입니다.

        Returns:
            BackgroundJob | None: 작업이 남아 있으면 작업 객체이고, 없으면 `None`입니다.
        """
        with self._lock:
            if self._prune_locked():
                self._persist_locked()
            return self._jobs.get(job_id)

    def list(self, problem_id: str | None = None) -> list[BackgroundJob]:
        """문제 식별자 조건에 맞는 작업 목록을 최신 실행 상태가 먼저 오도록 정렬해 반환합니다.

        Args:
            problem_id (str | None): 특정 문제의 작업만 조회할 때 사용할 문제 식별자입니다.

        Returns:
            list[BackgroundJob]: 정렬된 작업 객체 목록입니다.
        """
        with self._lock:
            if self._prune_locked():
                self._persist_locked()
            jobs = [
                job
                for job in self._jobs.values()
                if problem_id is None or job.problem_id == problem_id
            ]
        return sorted(jobs, key=self._sort_key)

    def dismiss(self, job_id: str) -> bool:
        """완료된 작업 하나를 사용자가 닫을 수 있도록 저장소에서 제거합니다. 실행 중인 작업은 제거하지 않습니다.

        Args:
            job_id (str): 제거할 완료 작업 식별자입니다.

        Returns:
            bool: 작업이 제거되었으면 `True`, 제거할 수 없으면 `False`입니다.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in ACTIVE_STATUSES:
                return False
            self._tokens.pop(job_id, None)
            self._operations.pop(job_id, None)
            self._jobs.pop(job_id, None)
            self._persist_locked()
            return True

    def clear_completed(self, predicate: Callable[[BackgroundJob], bool] | None = None) -> int:
        """완료된 작업 중 선택 조건을 만족하는 항목을 저장소에서 일괄 제거합니다.

        Args:
            predicate (Callable[[BackgroundJob], bool] | None): 제거할 완료 작업을 추가로 필터링하는 함수입니다.

        Returns:
            int: 제거된 작업 수입니다.
        """
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
            if removable:
                self._persist_locked()
            return len(removable)

    def cancel(self, job_id: str) -> bool:
        """대기 중인 작업은 즉시 취소 처리하고, 실행 중인 취소 가능 작업에는 취소 토큰을 전달합니다.

        Args:
            job_id (str): 취소할 백그라운드 작업 식별자입니다.

        Returns:
            bool: 취소 요청이 받아들여졌으면 `True`, 대상이 없거나 취소할 수 없으면 `False`입니다.
        """
        start_after: list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]] = []
        terminal_callback = None
        terminal_job = None
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            now = datetime.now(UTC)
            if job.status == "queued":
                queued_operation = self._operations.get(job_id)
                terminal_callback = (
                    queued_operation.terminal_callback if queued_operation is not None else None
                )
                job.status = "cancelled"
                job.cancel_requested = True
                job.cancelled_at = now
                job.finished_at = now
                job.updated_at = now
                self._operations.pop(job_id, None)
                self._tokens.pop(job_id, None)
                terminal_job = job
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
            self._persist_locked()
        if terminal_callback is not None and terminal_job is not None:
            try:
                terminal_callback(terminal_job)
            except Exception:  # noqa: BLE001 - terminal observers cannot break the queue.
                pass
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
        """작업의 진행률, 진행 메시지, 최근 로그를 갱신해 API 조회와 화면 표시가 같은 상태를 보도록 합니다.

        Args:
            job_id (str): 진행 상태를 갱신할 작업 식별자입니다.
            message (str | None): 최근 로그와 진행 메시지에 기록할 문구입니다.
            current (int | None): 현재 처리한 항목 수입니다.
            total (int | None): 전체 처리 대상 수입니다.
            label (str | None): 진행률이 어떤 단계를 의미하는지 설명하는 라벨입니다.
            extra (dict[str, Any] | None): 진행 상태 사전에 병합할 추가 값입니다.
        """
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
            self._persist_locked()

    def job_dict(self, job: BackgroundJob) -> dict[str, Any]:
        """저장소의 TTL 정책을 적용해 작업 객체를 API 응답 사전으로 변환합니다.

        Args:
            job (BackgroundJob): 응답으로 직렬화할 작업 객체입니다.

        Returns:
            dict[str, Any]: 클라이언트에 전달할 작업 상태 사전입니다.
        """
        return job.to_dict(ttl_seconds=self.ttl_seconds)

    def _result_indicates_failure(self, result: dict[str, Any] | None) -> bool:
        if not isinstance(result, dict):
            return False
        return result.get("passed") is False or bool(result.get("failureDetails"))

    def _normalize_failure_details(self, details: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        if not isinstance(details, list):
            return normalized
        for item in details:
            if isinstance(item, dict):
                normalized.append(dict(item))
            elif item is not None:
                normalized.append({"message": str(item)})
        return normalized

    def _failure_details_from_result(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        details = self._normalize_failure_details(result.get("failureDetails"))
        if details:
            return details
        problems = result.get("problems")
        if not isinstance(problems, list):
            return []
        for problem in problems:
            if not isinstance(problem, dict) or problem.get("passed") is not False:
                continue
            problem_details = self._normalize_failure_details(problem.get("failureDetails"))
            if problem_details:
                for detail in problem_details:
                    detail.setdefault("problemId", problem.get("problemId"))
                    detail.setdefault("label", problem.get("failureStageLabel") or "문제 실패")
                details.extend(problem_details)
                continue
            details.append(
                {
                    "problemId": problem.get("problemId"),
                    "label": problem.get("failureStageLabel") or "문제 실패",
                    "target": problem.get("problemId") or "",
                    "message": str(problem.get("summary") or "문제 검증이 실패했습니다."),
                }
            )
        return details

    def _target_label(self, job: BackgroundJob) -> str:
        target = job.target or {}
        return " · ".join(
            str(value)
            for value in [
                target.get("problemId") or job.problem_id,
                target.get("profile"),
                target.get("tool"),
                target.get("packId"),
                target.get("source"),
            ]
            if value
        )

    def _apply_result_failure_payload(
        self,
        job: BackgroundJob,
        result: dict[str, Any],
    ) -> None:
        details = self._failure_details_from_result(result)
        nested_stage = ""
        problems = result.get("problems")
        if isinstance(problems, list):
            nested_stage = next(
                (
                    str(problem.get("failureStage") or "")
                    for problem in problems
                    if isinstance(problem, dict) and problem.get("failureStage")
                ),
                "",
            )
        stage = str(
            result.get("failureStage")
            or nested_stage
            or infer_failure_stage(job.kind, job.title, job.progress.get("label"), job.last_log)
        )
        label = str(
            result.get("failureStageLabel")
            or job.progress.get("label")
            or stage_label(stage)
            or "작업 결과"
        )
        if not details:
            details = [
                {
                    "label": label,
                    "target": self._target_label(job),
                    "message": str(
                        result.get("summary")
                        or result.get("message")
                        or "확인할 실패 결과가 있습니다."
                    ),
                }
            ]
        job.outcome = "failed"
        job.error_kind = "validation-mismatch"
        job.failure_stage = stage
        job.failure_stage_label = label
        job.failure_details = details

    def _apply_exception_failure_payload(self, job: BackgroundJob, error: str) -> None:
        progress = job.progress or {}
        stage = str(
            progress.get("failureStage")
            or progress.get("stage")
            or infer_failure_stage(
                job.kind,
                job.title,
                progress.get("label"),
                progress.get("message"),
                job.last_log,
                error,
            )
        )
        label = str(
            progress.get("failureStageLabel")
            or progress.get("label")
            or job.title
            or stage_label(stage)
        )
        job.outcome = "failed"
        job.error_kind = "exception"
        job.failure_stage = stage
        job.failure_stage_label = label
        job.failure_details = [
            {
                "type": stage,
                "label": label,
                "target": self._target_label(job),
                "message": error,
                "lastLog": job.last_log,
            }
        ]

    def _finish(
        self,
        job_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """작업의 최종 상태, 결과, 오류를 기록하고 후속 대기 작업을 시작할 수 있도록 실행 슬롯을 비웁니다.

        Args:
            job_id (str): 완료 처리할 백그라운드 작업 식별자입니다.
            status (str): 기록할 최종 상태입니다.
            result (dict[str, Any] | None): 성공 시 작업 함수가 반환한 결과 데이터입니다.
            error (str | None): 실패 시 화면과 로그에 표시할 오류 메시지입니다.
        """
        terminal_callback = None
        terminal_job = None
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            now = datetime.now(UTC)
            job.status = status
            job.result = result
            job.error = error
            job.outcome = None
            job.error_kind = None
            job.failure_stage = None
            job.failure_stage_label = None
            job.failure_details = []
            job.finished_at = now
            job.updated_at = now
            if status == "cancelled":
                job.cancel_requested = True
                job.cancelled_at = job.cancelled_at or now
                job.outcome = "cancelled"
            if status == "failed":
                detail = error or "작업이 실패했습니다."
                self._apply_exception_failure_payload(job, detail)
                self._append_log_locked(job, detail)
            elif status == "succeeded" and self._result_indicates_failure(result):
                self._apply_result_failure_payload(job, result or {})
            elif status == "succeeded":
                job.outcome = "passed"
            self._tokens.pop(job_id, None)
            queued_operation = self._operations.pop(job_id, None)
            if queued_operation is not None:
                terminal_callback = queued_operation.terminal_callback
                terminal_job = job
            self._prune_locked()
            starts = self._ready_jobs_locked()
            self._persist_locked()
        if terminal_callback is not None and terminal_job is not None:
            try:
                terminal_callback(terminal_job)
            except Exception:  # noqa: BLE001 - terminal observers cannot break the queue.
                pass
        self._spawn_jobs(starts)

    def _ready_jobs_locked(
        self,
    ) -> list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]]:
        """현재 실행 슬롯과 레인 제한을 기준으로 바로 시작할 수 있는 대기 작업들을 선택합니다. 호출자는 저장소 락을 보유해야 합니다.

        Returns:
            list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]]: 시작할 작업, 취소 토큰, 실행 함수 묶음 목록입니다.
        """
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
        """대기열에서 전역 실행 제한과 레인별 제한을 모두 만족하는 다음 작업을 찾습니다. 호출자는 저장소 락을 보유해야 합니다.

        Args:
            planned (list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]]): 이번 스케줄링 라운드에서 이미 시작 대상으로 선택한 작업 목록입니다.

        Returns:
            BackgroundJob | None: 시작 가능한 다음 작업입니다. 없으면 `None`입니다.
        """
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
        """저장소 락 안에서 시작 가능한 작업을 고른 뒤 락 밖에서 백그라운드 스레드를 생성합니다."""
        with self._lock:
            starts = self._ready_jobs_locked()
            if starts:
                self._persist_locked()
        self._spawn_jobs(starts)

    def _spawn_jobs(
        self, starts: list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]]
    ) -> None:
        """선택된 작업 실행 묶음마다 데몬 스레드를 생성해 실제 작업 함수를 실행합니다.

        Args:
            starts (list[tuple[BackgroundJob, CancelToken | None, _QueuedOperation]]): 시작할 작업, 취소 토큰, 실행 함수 묶음 목록입니다.
        """
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
        """백그라운드 스레드에서 작업 함수를 실행하고 성공, 실패, 취소 상태를 저장소에 반영합니다.

        Args:
            job_id (str): 실행 중인 백그라운드 작업 식별자입니다.
            token (CancelToken | None): 취소 가능 작업에 전달할 취소 토큰입니다.
            operation (_QueuedOperation): 실행 함수와 취소 지원 여부를 담은 큐 항목입니다.
        """
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
            self._finish(job_id, "failed", error=str(exc) or exc.__class__.__name__)

    def _append_log_locked(self, job: BackgroundJob, message: str) -> None:
        """작업의 최근 로그 목록에 메시지를 추가하고 보존 개수 제한을 넘는 오래된 로그를 제거합니다. 호출자는 저장소 락을 보유해야 합니다.

        Args:
            job (BackgroundJob): 로그를 추가할 작업 객체입니다.
            message (str): 최근 로그에 기록할 메시지입니다.
        """
        job.last_log = message
        job.logs.append(
            {
                "message": message,
                "createdAt": datetime.now(UTC).isoformat(),
            }
        )
        if len(job.logs) > self.recent_log_limit:
            del job.logs[: len(job.logs) - self.recent_log_limit]

    def _prune_locked(self) -> bool:
        """저장된 작업 수가 보존 한도를 넘으면 가장 오래된 완료 작업부터 제거합니다. 호출자는 저장소 락을 보유해야 합니다."""
        if self.max_jobs <= 0:
            return False
        if len(self._jobs) <= self.max_jobs:
            return False
        changed = False
        completed = sorted(
            (job for job in self._jobs.values() if job.status in TERMINAL_STATUSES),
            key=lambda job: job.updated_at,
        )
        while len(self._jobs) > self.max_jobs and completed:
            oldest = completed.pop(0)
            self._jobs.pop(oldest.job_id, None)
            self._tokens.pop(oldest.job_id, None)
            self._operations.pop(oldest.job_id, None)
            changed = True
        return changed

    @staticmethod
    def _sort_key(job: BackgroundJob) -> tuple[int, datetime]:
        """작업 목록 정렬을 위해 실행 중, 대기 중, 완료 순서와 각 상태의 기준 시각을 계산합니다.

        Args:
            job (BackgroundJob): 정렬 키를 계산할 작업 객체입니다.

        Returns:
            tuple[int, datetime]: 작업 목록 정렬에 사용할 상태 우선순위와 시각 값입니다.
        """
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
    "INTERRUPTED_JOB_MESSAGE",
    "JOB_HISTORY_SCHEMA_VERSION",
    "JobCancelledError",
    "TERMINAL_STATUSES",
]
