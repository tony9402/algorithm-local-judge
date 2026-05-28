"""problems 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from judge.core.problem_folders import update_problem_folder
from judge.web import services
from judge.web.routes.common import etag_matches, to_http_error
from judge.web.schemas import ProblemFolderUpdateRequest
from judge.web.security_policy import ensure_local_web_action_allowed, ensure_remote_run_allowed

router = APIRouter(prefix="/api", tags=["problems"])


@router.get("/problems")
def api_problems() -> list[dict]:
    """api_problems 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        list[dict]: 처리 결과를 반환합니다.
    """
    try:
        return services.list_problems()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.patch("/problems/{problem_id}/folder")
def api_problem_folder_update(
    request: Request,
    problem_id: str,
    body: ProblemFolderUpdateRequest,
) -> dict:
    """api_problem_folder_update 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (ProblemFolderUpdateRequest): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        ensure_local_web_action_allowed(request, "problem folder editing")
        return update_problem_folder(problem_id, body.folder)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/problems/{problem_id}/samples")
def api_problem_samples(
    request: Request,
    problem_id: str,
    force: bool = Query(default=False),
) -> Response:
    """api_problem_samples 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        force (bool): `force` 값입니다.
    
    Returns:
        Response: 처리 결과를 반환합니다.
    """
    try:
        ensure_remote_run_allowed(request)
        result = services.sample_cases(problem_id, force)
        etag = str(result.get("etag", ""))
        headers = {"Cache-Control": "private, max-age=0, must-revalidate"}
        if etag:
            headers["ETag"] = etag
        if not force and etag_matches(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)
        return JSONResponse(result, headers=headers)
    except Exception as exc:
        raise to_http_error(exc) from exc
