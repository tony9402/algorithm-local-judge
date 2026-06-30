"""common API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from fastapi import HTTPException, Request

from alj_core.errors import (
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
    """FastAPI 앱 상태에서 현재 Problem Studio 작업 공간 경로를 꺼냅니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        Path: 검증된 작업 공간 요청 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    return request.app.state.workspace


def workspace_root_from_request(request: Request) -> Path:
    """작업 공간 root 요청 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        Path: 검증된 작업 공간 root 요청 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    return getattr(request.app.state, "workspace_root", request.app.state.workspace)


def active_repository_from_request(request: Request) -> str | None:
    """활성 저장소 요청 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

        Args:
            request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
    """
    return getattr(request.app.state, "active_repository", None)


def set_active_repository(request: Request, repo_name: str | None) -> Path:
    """활성 저장소 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        repo_name (str | None): 저장소 이름를 사용자 표시와 내부 조회에 함께 사용하는 이름입니다.

    Returns:
        Path: 검증된 활성 저장소 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    workspace_root = workspace_root_from_request(request)
    active = validate_repository_name(repo_name) if repo_name else None
    workspace = repository_mode_workspace(workspace_root, active)
    request.app.state.active_repository = active
    request.app.state.workspace = workspace
    return workspace


def repository_scope_from_request(request: Request) -> str:
    """저장소 scope 요청 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 저장소 scope 요청 문자열입니다.
    """
    active = active_repository_from_request(request)
    return f"repo:{active}" if active else "legacy"


def scoped_lane(request: Request, *parts: str) -> str:
    """scoped lane 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        *parts (str): scoped lane을 계산하거나 검증할 때 필요한 parts 입력입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 scoped lane 문자열입니다.
    """
    suffix = ":".join(part for part in parts if part)
    return f"problem-studio:{repository_scope_from_request(request)}:{suffix}"


def scoped_target(request: Request, target: dict | None = None) -> dict:
    """scoped target 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        target (dict | None): 파일을 복사하거나 산출물을 배치할 대상 경로입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 scoped target 데이터입니다.
    """
    active = active_repository_from_request(request)
    return {
        **(target or {}),
        "repositoryName": active,
        "repositoryScope": repository_scope_from_request(request),
        "repositoryPath": str(workspace_from_request(request)),
    }


def job_matches_active_repository(request: Request, job: BackgroundJob) -> bool:
    """작업 matches 활성 저장소 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        job (BackgroundJob): 작업 matches 활성 저장소을 계산하거나 검증할 때 필요한 작업 입력입니다.

    Returns:
        bool: 작업 matches 활성 저장소 조건을 만족하면 True, 아니면 False입니다.
    """
    target = job.target or {}
    repository_scope = target.get("repositoryScope")
    if repository_scope is None:
        return active_repository_from_request(request) is None
    return repository_scope == repository_scope_from_request(request)


def jobs_from_request(request: Request) -> BackgroundJobStore:
    """작업 요청 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

        Args:
            request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
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
    """background 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

        Args:
            jobs (BackgroundJobStore): background 작업을 계산하거나 검증할 때 필요한 작업 입력입니다.
            request (Request | None): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
            kind (str): background 작업을 계산하거나 검증할 때 필요한 kind 입력입니다.
            title (str): background 작업을 계산하거나 검증할 때 필요한 title 입력입니다.
            problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
            lane (str): background 작업을 계산하거나 검증할 때 필요한 lane 입력입니다.
            target (dict | None): 파일을 복사하거나 산출물을 배치할 대상 경로입니다.
            operation (Callable[[CancelToken, Callable[..., None]], dict]): background 작업을 계산하거나 검증할 때 필요한 operation 입력입니다.
            app (str): background 작업을 계산하거나 검증할 때 필요한 애플리케이션 입력입니다.
            result_actions (dict | None): background 작업을 계산하거나 검증할 때 필요한 결과 actions 입력입니다.
            input_snapshot_summary (str | None): background 작업을 계산하거나 검증할 때 필요한 입력 snapshot summary 입력입니다.
    """
    return jobs.start_with_progress(
        kind=kind,
        title=title,
        problem_id=problem_id,
        operation=operation,
        app=app,
        lane=lane,
        target=scoped_target(request, target) if request is not None else target,
        result_actions=result_actions,
        input_snapshot_summary=input_snapshot_summary,
    )


def add_workspace_warning(request: Request, status: dict) -> dict:
    """add 작업 공간 warning 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        status (dict): add 작업 공간 warning을 계산하거나 검증할 때 필요한 상태 입력입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 add 작업 공간 warning 데이터입니다.
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
    """요청의 앱 상태와 활성 저장소를 기준으로 프론트엔드가 표시할 작업 공간 상태를 구성합니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 공간 상태 요청 데이터입니다.
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
    """http 오류 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        exc (Exception): http 오류을 계산하거나 검증할 때 필요한 exc 입력입니다.

    Returns:
        HTTPException: 클라이언트에 전달할 상태 코드와 오류 본문을 담은 HTTP 예외입니다.
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
    """라우트 내부 작업의 JudgeError와 예상 가능한 예외를 JSON HTTP 오류 응답으로 변환합니다.

        Args:
            operation (Callable[[], T]): 라우트 결과을 계산하거나 검증할 때 필요한 operation 입력입니다.
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
