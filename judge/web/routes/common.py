"""common 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
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
    """to_http_error 함수를 실행하고 결과를 반환합니다.
    
    Args:
        exc (Exception): `exc` 값입니다.
    
    Returns:
        HTTPException: 처리 결과를 반환합니다.
    """
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
    """jobs_from_request 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        BackgroundJobStore: 처리 결과를 반환합니다.
    """
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
    """enqueue_background_job 함수를 실행하고 결과를 반환합니다.
    
    Args:
        jobs (BackgroundJobStore): `jobs` 값입니다.
        kind (str): `kind` 값입니다.
        title (str): `title` 값입니다.
        problem_id (str): 문제 ID입니다.
        lane (str): `lane` 값입니다.
        target (dict | None): `target` 값입니다.
        operation (Callable[[CancelToken, Callable[..., None]], dict]): `operation` 값입니다.
        app (str): `app` 값입니다.
        result_actions (dict | None): `result_actions` 값입니다.
        input_snapshot_summary (str | None): `input_snapshot_summary` 값입니다.
        cancel_supported (bool): `cancel_supported` 값입니다.
        cancel_mode (str): `cancel_mode` 값입니다.
        cancel_blocked_reason (str | None): `cancel_blocked_reason` 값입니다.
    
    Returns:
        BackgroundJob: 처리 결과를 반환합니다.
    """
    holder: dict[str, str] = {}
    ready = threading.Event()

    def run(cancel_token: CancelToken | None = None) -> dict:
    """run 함수를 실행하고 결과를 반환합니다.
    
    Args:
        cancel_token (CancelToken | None): `cancel_token` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
        ready.wait(timeout=2)
        token = cancel_token or CancelToken()

        def progress(
            message: str,
            current: int | None = None,
            total: int | None = None,
            label: str | None = None,
            **extra,
        ) -> None:
        """progress 함수를 실행하고 결과를 반환합니다.
        
        Args:
            message (str): 메시지입니다.
            current (int | None): `current` 값입니다.
            total (int | None): `total` 값입니다.
            label (str | None): `label` 값입니다.
            **extra (Any): `extra` 값입니다.
        
        Returns:
            None: 처리 결과를 반환합니다.
        """
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
    """etag_matches 함수를 실행하고 결과를 반환합니다.
    
    Args:
        header (str | None): `header` 값입니다.
        etag (str): `etag` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    if not header:
        return False
    return any(item.strip() == etag or item.strip() == "*" for item in header.split(","))
