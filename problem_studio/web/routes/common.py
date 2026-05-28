"""common 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from fastapi import HTTPException, Request

from judge.core.errors import (
    ConcurrencyLimitError,
    JudgeError,
    LimitExceededError,
    SecurityPolicyError,
)
from problem_studio.core.workspace import workspace_status
from problem_studio.core.repositories import (
    repository_context,
    repository_mode_workspace,
    validate_repository_name,
)
from problem_studio.web.jobs import BackgroundJob, BackgroundJobStore, CancelToken
from problem_studio.web.streaming import sse, stream_operation

T = TypeVar("T")


def workspace_from_request(request: Request) -> Path:
    """workspace_from_request 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    return request.app.state.workspace


def workspace_root_from_request(request: Request) -> Path:
    """workspace_root_from_request 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    return getattr(request.app.state, "workspace_root", request.app.state.workspace)


def active_repository_from_request(request: Request) -> str | None:
    """active_repository_from_request 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        str | None: 처리 결과를 반환합니다.
    """
    return getattr(request.app.state, "active_repository", None)


def set_active_repository(request: Request, repo_name: str | None) -> Path:
    """set_active_repository 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        repo_name (str | None): `repo_name` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    workspace_root = workspace_root_from_request(request)
    active = validate_repository_name(repo_name) if repo_name else None
    workspace = repository_mode_workspace(workspace_root, active)
    request.app.state.active_repository = active
    request.app.state.workspace = workspace
    return workspace


def repository_scope_from_request(request: Request) -> str:
    """repository_scope_from_request 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    active = active_repository_from_request(request)
    return f"repo:{active}" if active else "legacy"


def scoped_lane(request: Request, *parts: str) -> str:
    """scoped_lane 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        *parts (str): `parts` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    suffix = ":".join(part for part in parts if part)
    return f"problem-studio:{repository_scope_from_request(request)}:{suffix}"


def scoped_target(request: Request, target: dict | None = None) -> dict:
    """scoped_target 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        target (dict | None): `target` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    active = active_repository_from_request(request)
    return {
        **(target or {}),
        "repositoryName": active,
        "repositoryScope": repository_scope_from_request(request),
        "repositoryPath": str(workspace_from_request(request)),
    }


def job_matches_active_repository(request: Request, job: BackgroundJob) -> bool:
    """job_matches_active_repository 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        job (BackgroundJob): `job` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    target = job.target or {}
    repository_scope = target.get("repositoryScope")
    if repository_scope is None:
        return active_repository_from_request(request) is None
    return repository_scope == repository_scope_from_request(request)


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
    request: Request | None = None,
    kind: str,
    title: str,
    problem_id: str,
    lane: str,
    target: dict | None,
    operation: Callable[[CancelToken, Callable[..., None]], dict],
    app: str = "problem_studio",
    result_actions: dict | None = None,
    input_snapshot_summary: str | None = None,
) -> BackgroundJob:
    """enqueue_background_job 함수를 실행하고 결과를 반환합니다.
    
    Args:
        jobs (BackgroundJobStore): `jobs` 값입니다.
        request (Request | None): HTTP 요청 객체입니다.
        kind (str): `kind` 값입니다.
        title (str): `title` 값입니다.
        problem_id (str): 문제 ID입니다.
        lane (str): `lane` 값입니다.
        target (dict | None): `target` 값입니다.
        operation (Callable[[CancelToken, Callable[..., None]], dict]): `operation` 값입니다.
        app (str): `app` 값입니다.
        result_actions (dict | None): `result_actions` 값입니다.
        input_snapshot_summary (str | None): `input_snapshot_summary` 값입니다.
    
    Returns:
        BackgroundJob: 처리 결과를 반환합니다.
    """
    holder: dict[str, str] = {}
    ready = threading.Event()

    def run(cancel_token: CancelToken) -> dict:
    """run 함수를 실행하고 결과를 반환합니다.
    
    Args:
        cancel_token (CancelToken): `cancel_token` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
        ready.wait(timeout=2)

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
            cancel_token.check()
            jobs.update_progress(
                holder["job_id"],
                message,
                current=current,
                total=total,
                label=label,
                extra=extra or None,
            )

        return operation(cancel_token, progress)

    job = jobs.start(
        kind=kind,
        title=title,
        problem_id=problem_id,
        operation=run,
        cancel_supported=True,
        app=app,
        lane=lane,
        target=scoped_target(request, target) if request is not None else target,
        result_actions=result_actions,
        input_snapshot_summary=input_snapshot_summary,
    )
    holder["job_id"] = job.job_id
    ready.set()
    return job


def add_workspace_warning(request: Request, status: dict) -> dict:
    """add_workspace_warning 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        status (dict): `status` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    status = {
        **status,
        "writeEnabled": bool(getattr(request.app.state, "workspace_write_enabled", True)),
    }
    if not getattr(request.app.state, "workspace_warning", False):
        return status
    return {
        **status,
        "warning": {
            "kind": "nonLocalBinding",
            "title": "Non-local workspace access",
            "message": (
                "이 서버는 로컬 전용 주소가 아닌 곳에 bind되어 있습니다. "
                "워크스페이스 열기와 파일 저장 API는 기본 차단됩니다."
            ),
        },
    }


def workspace_status_from_request(request: Request) -> dict:
    """workspace_status_from_request 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    status = workspace_status(workspace_from_request(request))
    status.update(
        repository_context(
            workspace_root_from_request(request),
            active_repository_from_request(request),
        )
    )
    return add_workspace_warning(request, status)


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


def route_result(operation: Callable[[], T]) -> T:
    """route_result 함수를 실행하고 결과를 반환합니다.
    
    Args:
        operation (Callable[[], T]): `operation` 값입니다.
    
    Returns:
        T: 처리 결과를 반환합니다.
    """
    try:
        return operation()
    except Exception as exc:
        raise to_http_error(exc) from exc


__all__ = [
    "add_workspace_warning",
    "active_repository_from_request",
    "enqueue_background_job",
    "job_matches_active_repository",
    "jobs_from_request",
    "route_result",
    "repository_scope_from_request",
    "scoped_lane",
    "scoped_target",
    "set_active_repository",
    "sse",
    "stream_operation",
    "to_http_error",
    "workspace_from_request",
    "workspace_root_from_request",
    "workspace_status_from_request",
]
