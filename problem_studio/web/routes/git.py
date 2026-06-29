"""Git API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from alj_core.errors import JudgeError
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
    """Git 쓰기 enabled 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
    """
    ensure_local_write_allowed(request, "Git network/write action")
    if not getattr(request.app.state, "git_write_enabled", True):
        raise JudgeError("Git network/write actions are disabled for this server binding")


def attach_git_write_policy(request: Request, status: dict) -> dict:
    """attach Git 쓰기 정책 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        status (dict): attach Git 쓰기 정책을 계산하거나 검증할 때 필요한 상태 입력입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 attach Git 쓰기 정책 데이터입니다.
    """
    status["writeEnabled"] = bool(getattr(request.app.state, "git_write_enabled", True))
    status["workspaceRoot"] = str(workspace_root_from_request(request))
    status["repositoryName"] = active_repository_from_request(request)
    status["repositoryPath"] = str(workspace_from_request(request))
    status["repositoryMode"] = active_repository_from_request(request) is not None
    return status


def status_payload(request: Request) -> dict:
    """상태 payload 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 상태 payload 데이터입니다.
    """
    return attach_git_write_policy(request, git_status(workspace_from_request(request)))


@router.get("/status")
def api_git_status(request: Request) -> dict:
    """Git 상태 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 Git 상태 데이터입니다.
    """
    return route_result(lambda: status_payload(request))


@router.post("/clone")
def api_git_clone(request: Request, body: GitCloneRequest) -> dict:
    """Git clone 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        body (GitCloneRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 Git clone 데이터입니다.
    """

    def operation() -> dict:
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
    """Git fetch 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 Git fetch 데이터입니다.
    """

    def operation() -> dict:
        ensure_git_write_enabled(request)
        return attach_git_write_policy(request, fetch_repository(workspace_from_request(request)))

    return route_result(operation)


@router.post("/pull")
def api_git_pull(request: Request) -> dict:
    """Git pull 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 Git pull 데이터입니다.
    """

    def operation() -> dict:
        ensure_git_write_enabled(request)
        return attach_git_write_policy(request, pull_repository(workspace_from_request(request)))

    return route_result(operation)


@router.post("/commit")
def api_git_commit(request: Request, body: GitCommitRequest) -> dict:
    """Git commit 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        body (GitCommitRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 Git commit 데이터입니다.
    """

    def operation() -> dict:
        ensure_git_write_enabled(request)
        return attach_git_write_policy(
            request,
            commit_changes(workspace_from_request(request), body.message, body.files),
        )

    return route_result(operation)


@router.post("/push")
def api_git_push(request: Request) -> dict:
    """Git push 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 Git push 데이터입니다.
    """

    def operation() -> dict:
        ensure_git_write_enabled(request)
        return attach_git_write_policy(request, push_repository(workspace_from_request(request)))

    return route_result(operation)
