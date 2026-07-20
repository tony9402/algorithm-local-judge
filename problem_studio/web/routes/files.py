"""파일 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다."""

from __future__ import annotations

from fastapi import APIRouter, Request

from problem_studio.core.editor import (
    list_problem_files,
    read_problem_file,
    write_problem_file,
)
from problem_studio.web.routes.common import route_result, workspace_from_request
from problem_studio.web.schemas import FileWriteRequest
from problem_studio.web.security_policy import (
    ensure_local_web_action_allowed,
    ensure_local_write_allowed,
)

router = APIRouter(prefix="/api/problems/{problem_id}/files", tags=["files"])


@router.get("")
def api_problem_files(request: Request, problem_id: str) -> dict:
    """문제 파일 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 파일 데이터입니다.
    """
    return route_result(
        lambda: (
            ensure_local_web_action_allowed(request, "problem file listing read")
            or {"files": list_problem_files(workspace_from_request(request), problem_id)}
        )
    )


@router.get("/{file_path:path}")
def api_problem_file_read(request: Request, problem_id: str, file_path: str) -> dict:
    """문제 파일 읽기 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        file_path (str): 파일 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 파일 읽기 데이터입니다.
    """
    return route_result(
        lambda: (
            ensure_local_web_action_allowed(request, "problem file read")
            or read_problem_file(workspace_from_request(request), problem_id, file_path)
        )
    )


@router.put("/{file_path:path}")
def api_problem_file_write(
    request: Request, problem_id: str, file_path: str, body: FileWriteRequest
) -> dict:
    """문제 파일 쓰기 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        file_path (str): 파일 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        body (FileWriteRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 파일 쓰기 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "file write")
        return write_problem_file(
            workspace_from_request(request), problem_id, file_path, body.content
        )

    return route_result(operation)
