"""repositories 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from judge.core.errors import JudgeError
from problem_studio.core.git import git_status
from problem_studio.core.repositories import (
    clone_problem_repository,
    list_repositories,
    repository_summary,
)
from problem_studio.web.routes.common import (
    active_repository_from_request,
    route_result,
    set_active_repository,
    workspace_root_from_request,
    workspace_status_from_request,
)
from problem_studio.web.schemas import (
    RepositoryCloneRequest,
    RepositoryRegisterRequest,
    RepositorySelectRequest,
)
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


def ensure_repository_write_enabled(request: Request) -> None:
    """ensure_repository_write_enabled 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    ensure_local_write_allowed(request, "repository Git action")
    if not getattr(request.app.state, "git_write_enabled", True):
        raise JudgeError("Git network/write actions are disabled for this server binding")


def repository_response(request: Request) -> dict:
    """repository_response 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    workspace_root = workspace_root_from_request(request)
    return {
        "workspaceRoot": str(workspace_root),
        "activeRepository": active_repository_from_request(request),
        "repositoryMode": active_repository_from_request(request) is not None,
        "repositories": list_repositories(workspace_root),
    }


def selected_payload(request: Request) -> dict:
    """selected_payload 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    workspace = workspace_status_from_request(request)
    git = git_status(request.app.state.workspace)
    git["writeEnabled"] = bool(getattr(request.app.state, "git_write_enabled", True))
    git["workspaceRoot"] = workspace["workspaceRoot"]
    git["repositoryName"] = workspace["activeRepository"]
    git["repositoryPath"] = workspace["workspace"]
    git["repositoryMode"] = workspace["repositoryMode"]
    return {
        "workspace": workspace,
        "repositories": repository_response(request),
        "git": git,
    }


@router.get("")
def api_repositories(request: Request) -> dict:
    """api_repositories 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    return route_result(lambda: repository_response(request))


@router.post("/select")
def api_repository_select(request: Request, body: RepositorySelectRequest) -> dict:
    """api_repository_select 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        body (RepositorySelectRequest): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """

    def operation() -> dict:
    """operation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
        set_active_repository(request, body.repo_name)
        return selected_payload(request)

    return route_result(operation)


@router.post("/clone")
def api_repository_clone(request: Request, body: RepositoryCloneRequest) -> dict:
    """api_repository_clone 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        body (RepositoryCloneRequest): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """

    def operation() -> dict:
    """operation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
        ensure_repository_write_enabled(request)
        summary = clone_problem_repository(
            workspace_root_from_request(request),
            body.url,
            body.branch,
            body.repo_name,
        )
        set_active_repository(request, summary["name"])
        payload = selected_payload(request)
        payload["repository"] = summary
        return payload

    return route_result(operation)


@router.post("/register")
def api_repository_register(request: Request, body: RepositoryRegisterRequest) -> dict:
    """api_repository_register 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        body (RepositoryRegisterRequest): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """

    def operation() -> dict:
    """operation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
        set_active_repository(request, body.repo_name)
        payload = selected_payload(request)
        payload["repository"] = repository_summary(
            workspace_root_from_request(request),
            body.repo_name,
        )
        return payload

    return route_result(operation)
