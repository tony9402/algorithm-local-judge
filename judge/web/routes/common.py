from __future__ import annotations

import threading
from collections.abc import Callable

from fastapi import HTTPException, Request

from commons.job_queue import BackgroundJob, BackgroundJobStore, CancelToken
from judge.core.errors import (
    ConcurrencyLimitError,
    JudgeError,
    LimitExceededError,
    SecurityPolicyError,
)


def to_http_error(exc: Exception) -> HTTPException:
    """Convert domain errors into JSON HTTP responses."""
    if isinstance(exc, SecurityPolicyError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LimitExceededError):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, ConcurrencyLimitError):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, JudgeError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def jobs_from_request(request: Request) -> BackgroundJobStore:
    """Return the in-memory web job queue."""
    return request.app.state.jobs


def enqueue_background_job(
    jobs: BackgroundJobStore,
    *,
    kind: str,
    title: str,
    problem_id: str,
    lane: str,
    target: dict | None,
    operation: Callable[[CancelToken, Callable[..., None]], dict],
    app: str = "judge",
    result_actions: dict | None = None,
    input_snapshot_summary: str | None = None,
    cancel_supported: bool = True,
    cancel_mode: str = "cooperative",
    cancel_blocked_reason: str | None = None,
) -> BackgroundJob:
    """Start a queued Judge job with a progress callback bound to its id."""
    holder: dict[str, str] = {}
    ready = threading.Event()

    def run(cancel_token: CancelToken | None = None) -> dict:
        ready.wait(timeout=2)
        token = cancel_token or CancelToken()

        def progress(
            message: str,
            current: int | None = None,
            total: int | None = None,
            label: str | None = None,
            **extra,
        ) -> None:
            token.check()
            jobs.update_progress(
                holder["job_id"],
                message,
                current=current,
                total=total,
                label=label,
                extra=extra or None,
            )

        return operation(token, progress)

    job = jobs.start(
        kind=kind,
        title=title,
        problem_id=problem_id,
        operation=run,
        cancel_supported=cancel_supported,
        app=app,
        lane=lane,
        target=target,
        result_actions=result_actions,
        input_snapshot_summary=input_snapshot_summary,
        cancel_mode=cancel_mode,
        cancel_blocked_reason=cancel_blocked_reason,
    )
    holder["job_id"] = job.job_id
    ready.set()
    return job


def etag_matches(header: str | None, etag: str) -> bool:
    """Return whether an If-None-Match header contains the current ETag."""
    if not header:
        return False
    return any(item.strip() == etag or item.strip() == "*" for item in header.split(","))
