"""저장소 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
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
    """저장소 쓰기 enabled 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
    """
    ensure_local_write_allowed(request, "repository Git action")
    if not getattr(request.app.state, "git_write_enabled", True):
        raise JudgeError("Git network/write actions are disabled for this server binding")


def repository_response(request: Request) -> dict:
    """저장소 response 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 저장소 response 데이터입니다.
    """
    workspace_root = workspace_root_from_request(request)
    return {
        "workspaceRoot": str(workspace_root),
        "activeRepository": active_repository_from_request(request),
        "repositoryMode": active_repository_from_request(request) is not None,
        "repositories": list_repositories(workspace_root),
    }


def selected_payload(request: Request) -> dict:
    """selected payload 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 selected payload 데이터입니다.
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
    """저장소 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 저장소 데이터입니다.
    """
    return route_result(lambda: repository_response(request))


@router.post("/select")
def api_repository_select(request: Request, body: RepositorySelectRequest) -> dict:
    """저장소 select 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        body (RepositorySelectRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 저장소 select 데이터입니다.
    """

    def operation() -> dict:
        set_active_repository(request, body.repo_name)
        return selected_payload(request)

    return route_result(operation)


@router.post("/clone")
def api_repository_clone(request: Request, body: RepositoryCloneRequest) -> dict:
    """저장소 clone 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        body (RepositoryCloneRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 저장소 clone 데이터입니다.
    """

    def operation() -> dict:
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
    """저장소 register 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        body (RepositoryRegisterRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 저장소 register 데이터입니다.
    """

    def operation() -> dict:
        set_active_repository(request, body.repo_name)
        payload = selected_payload(request)
        payload["repository"] = repository_summary(
            workspace_root_from_request(request),
            body.repo_name,
        )
        return payload

    return route_result(operation)
