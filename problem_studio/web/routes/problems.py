"""문제 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from alj_core.problem import load_problem
from problem_studio.core.editor import list_problem_files, update_problem_metadata
from problem_studio.core.templates import create_problem
from problem_studio.core.workspace import (
    delete_problem,
    list_problem_metadata,
    rename_problem,
)
from problem_studio.web.routes.common import (
    add_workspace_warning,
    route_result,
    workspace_from_request,
    workspace_status_from_request,
)
from problem_studio.web.schemas import (
    MetadataPatchRequest,
    ProblemCreateRequest,
    ProblemDeleteRequest,
    ProblemRenameRequest,
)
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/problems", tags=["problems"])


@router.get("")
def api_problems(request: Request) -> list[dict]:
    """문제 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        list[dict]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 데이터입니다.
    """
    return route_result(lambda: list_problem_metadata(workspace_from_request(request)))


@router.post("")
def api_problem_create(request: Request, body: ProblemCreateRequest) -> dict:
    """문제 create 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        body (ProblemCreateRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 create 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "problem creation")
        workspace = workspace_from_request(request)
        result = create_problem(
            workspace,
            body.problem_id,
            body.title,
            body.folder,
            body.version,
            body.default_profile,
            body.limits,
        )
        result["workspace"] = workspace_status_from_request(request)
        return result

    return route_result(operation)


@router.get("/{problem_id}")
def api_problem_detail(request: Request, problem_id: str) -> dict:
    """문제 detail 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 detail 데이터입니다.
    """

    def operation() -> dict:
        workspace = workspace_from_request(request)
        problem_dir, metadata_path, metadata = load_problem(problem_id, workspace)
        return {
            "problemId": problem_id,
            "path": str(problem_dir),
            "metadataPath": str(metadata_path),
            "metadata": metadata,
            "files": list_problem_files(workspace, problem_id),
        }

    return route_result(operation)


@router.patch("/{problem_id}/metadata")
def api_problem_metadata_patch(
    request: Request, problem_id: str, body: MetadataPatchRequest
) -> dict:
    """문제 메타데이터 patch 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (MetadataPatchRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 메타데이터 patch 데이터입니다.
    """
    return route_result(
        lambda: (
            ensure_local_write_allowed(request, "problem metadata update")
            or update_problem_metadata(workspace_from_request(request), problem_id, body.metadata)
        )
    )


@router.patch("/{problem_id}/id")
def api_problem_rename(request: Request, problem_id: str, body: ProblemRenameRequest) -> dict:
    """문제 rename 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (ProblemRenameRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 rename 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "problem rename")
        result = rename_problem(workspace_from_request(request), problem_id, body.problem_id)
        result["workspace"] = add_workspace_warning(request, result["workspace"])
        return result

    return route_result(operation)


@router.delete("/{problem_id}")
def api_problem_delete(request: Request, problem_id: str, body: ProblemDeleteRequest) -> dict:
    """문제 delete 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (ProblemDeleteRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 delete 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "problem delete")
        result = delete_problem(
            workspace_from_request(request),
            problem_id,
            body.confirm_phrase,
        )
        result["workspace"] = add_workspace_warning(request, result["workspace"])
        return result

    return route_result(operation)
