"""problems 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from judge.core.problem import load_problem
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
    """api_problems 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        list[dict]: 처리 결과를 반환합니다.
    """
    return route_result(lambda: list_problem_metadata(workspace_from_request(request)))


@router.post("")
def api_problem_create(request: Request, body: ProblemCreateRequest) -> dict:
    """api_problem_create 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        body (ProblemCreateRequest): `body` 값입니다.
    
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
    """api_problem_detail 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
    
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
    """api_problem_metadata_patch 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (MetadataPatchRequest): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    return route_result(
        lambda: (
            ensure_local_write_allowed(request, "problem metadata update")
            or update_problem_metadata(workspace_from_request(request), problem_id, body.metadata)
        )
    )


@router.patch("/{problem_id}/id")
def api_problem_rename(request: Request, problem_id: str, body: ProblemRenameRequest) -> dict:
    """api_problem_rename 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (ProblemRenameRequest): `body` 값입니다.
    
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
        ensure_local_write_allowed(request, "problem rename")
        result = rename_problem(workspace_from_request(request), problem_id, body.problem_id)
        result["workspace"] = add_workspace_warning(request, result["workspace"])
        return result

    return route_result(operation)


@router.delete("/{problem_id}")
def api_problem_delete(request: Request, problem_id: str, body: ProblemDeleteRequest) -> dict:
    """api_problem_delete 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (ProblemDeleteRequest): `body` 값입니다.
    
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
        ensure_local_write_allowed(request, "problem delete")
        result = delete_problem(
            workspace_from_request(request),
            problem_id,
            body.confirm_phrase,
        )
        result["workspace"] = add_workspace_warning(request, result["workspace"])
        return result

    return route_result(operation)
