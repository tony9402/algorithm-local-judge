"""files 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from problem_studio.core.editor import (
    list_problem_files,
    read_problem_file,
    write_problem_file,
)
from problem_studio.web.routes.common import route_result, workspace_from_request
from problem_studio.web.schemas import FileWriteRequest
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/problems/{problem_id}/files", tags=["files"])


@router.get("")
def api_problem_files(request: Request, problem_id: str) -> dict:
    """api_problem_files 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    return route_result(
        lambda: {"files": list_problem_files(workspace_from_request(request), problem_id)}
    )


@router.get("/{file_path:path}")
def api_problem_file_read(request: Request, problem_id: str, file_path: str) -> dict:
    """api_problem_file_read 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        file_path (str): `file_path` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    return route_result(
        lambda: read_problem_file(workspace_from_request(request), problem_id, file_path)
    )


@router.put("/{file_path:path}")
def api_problem_file_write(
    request: Request, problem_id: str, file_path: str, body: FileWriteRequest
) -> dict:
    """api_problem_file_write 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        file_path (str): `file_path` 값입니다.
        body (FileWriteRequest): `body` 값입니다.
    
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
        ensure_local_write_allowed(request, "file write")
        return write_problem_file(
            workspace_from_request(request), problem_id, file_path, body.content
        )

    return route_result(operation)
