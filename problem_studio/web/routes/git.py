"""git 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from judge.core.errors import JudgeError
from problem_studio.core.git import (
    clone_repository,
    commit_changes,
    fetch_repository,
    git_status,
    pull_repository,
    push_repository,
)
from problem_studio.core.workspace import workspace_status
from problem_studio.web.routes.common import (
    active_repository_from_request,
    add_workspace_warning,
    route_result,
    workspace_from_request,
    workspace_root_from_request,
)
from problem_studio.web.schemas import GitCloneRequest, GitCommitRequest
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/workspace/git", tags=["workspace-git"])


def ensure_git_write_enabled(request: Request) -> None:
    """ensure_git_write_enabled 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    ensure_local_write_allowed(request, "Git network/write action")
    if not getattr(request.app.state, "git_write_enabled", True):
        raise JudgeError("Git network/write actions are disabled for this server binding")


def attach_git_write_policy(request: Request, status: dict) -> dict:
    """attach_git_write_policy 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        status (dict): `status` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    status["writeEnabled"] = bool(getattr(request.app.state, "git_write_enabled", True))
    status["workspaceRoot"] = str(workspace_root_from_request(request))
    status["repositoryName"] = active_repository_from_request(request)
    status["repositoryPath"] = str(workspace_from_request(request))
    status["repositoryMode"] = active_repository_from_request(request) is not None
    return status


def status_payload(request: Request) -> dict:
    """status_payload 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    return attach_git_write_policy(request, git_status(workspace_from_request(request)))


@router.get("/status")
def api_git_status(request: Request) -> dict:
    """api_git_status 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    return route_result(lambda: status_payload(request))


@router.post("/clone")
def api_git_clone(request: Request, body: GitCloneRequest) -> dict:
    """api_git_clone 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        body (GitCloneRequest): `body` 값입니다.
    
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
        ensure_git_write_enabled(request)
        target = Path(body.path)
        clone_repository(body.url, target, body.branch)
        request.app.state.workspace_root = target.expanduser().resolve()
        request.app.state.active_repository = None
        request.app.state.workspace = request.app.state.workspace_root
        return {
            "workspace": add_workspace_warning(
                request,
                workspace_status(request.app.state.workspace),
            ),
            "git": status_payload(request),
        }

    return route_result(operation)


@router.post("/fetch")
def api_git_fetch(request: Request) -> dict:
    """api_git_fetch 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
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
        ensure_git_write_enabled(request)
        return attach_git_write_policy(request, fetch_repository(workspace_from_request(request)))

    return route_result(operation)


@router.post("/pull")
def api_git_pull(request: Request) -> dict:
    """api_git_pull 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
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
        ensure_git_write_enabled(request)
        return attach_git_write_policy(request, pull_repository(workspace_from_request(request)))

    return route_result(operation)


@router.post("/commit")
def api_git_commit(request: Request, body: GitCommitRequest) -> dict:
    """api_git_commit 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        body (GitCommitRequest): `body` 값입니다.
    
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
        ensure_git_write_enabled(request)
        return attach_git_write_policy(
            request,
            commit_changes(workspace_from_request(request), body.message, body.files),
        )

    return route_result(operation)


@router.post("/push")
def api_git_push(request: Request) -> dict:
    """api_git_push 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
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
        ensure_git_write_enabled(request)
        return attach_git_write_policy(request, push_repository(workspace_from_request(request)))

    return route_result(operation)
