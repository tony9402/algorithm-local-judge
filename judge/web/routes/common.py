"""common API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
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
    """http 오류 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        exc (Exception): http 오류을 계산하거나 검증할 때 필요한 exc 입력입니다.

    Returns:
        HTTPException: 클라이언트에 전달할 상태 코드와 오류 본문을 담은 HTTP 예외입니다.
    """
    if isinstance(exc, HTTPException):
        return exc
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
    """작업 요청 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

        Args:
            request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
    """
    return request.app.state.jobs


def record_submission_or_429(request: Request, problem_id: str) -> None:
    limiter = request.app.state.submission_rate_limiter
    decision = limiter.check_and_record(problem_id)
    if decision.accepted:
        return
    raise HTTPException(
        status_code=429,
        detail={
            "message": "같은 문제는 5초에 한 번만 제출할 수 있습니다.",
            "retryAfterSeconds": decision.retry_after_seconds,
        },
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )


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
    """background 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

        Args:
            jobs (BackgroundJobStore): background 작업을 계산하거나 검증할 때 필요한 작업 입력입니다.
            kind (str): background 작업을 계산하거나 검증할 때 필요한 kind 입력입니다.
            title (str): background 작업을 계산하거나 검증할 때 필요한 title 입력입니다.
            problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
            lane (str): background 작업을 계산하거나 검증할 때 필요한 lane 입력입니다.
            target (dict | None): 파일을 복사하거나 산출물을 배치할 대상 경로입니다.
            operation (Callable[[CancelToken, Callable[..., None]], dict]): background 작업을 계산하거나 검증할 때 필요한 operation 입력입니다.
            app (str): background 작업을 계산하거나 검증할 때 필요한 애플리케이션 입력입니다.
            result_actions (dict | None): background 작업을 계산하거나 검증할 때 필요한 결과 actions 입력입니다.
            input_snapshot_summary (str | None): background 작업을 계산하거나 검증할 때 필요한 입력 snapshot summary 입력입니다.
            cancel_supported (bool): background 작업 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
            cancel_mode (str): background 작업을 계산하거나 검증할 때 필요한 cancel mode 입력입니다.
            cancel_blocked_reason (str | None): background 작업을 계산하거나 검증할 때 필요한 cancel blocked reason 입력입니다.
    """
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
    """etag matches 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        header (str | None): etag matches을 계산하거나 검증할 때 필요한 header 입력입니다.
        etag (str): etag matches을 계산하거나 검증할 때 필요한 etag 입력입니다.

    Returns:
        bool: etag matches 조건을 만족하면 True, 아니면 False입니다.
    """
    if not header:
        return False
    return any(item.strip() == etag or item.strip() == "*" for item in header.split(","))
