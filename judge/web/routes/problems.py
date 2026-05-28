"""문제 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
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
    """문제 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Returns:
        list[dict]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 데이터입니다.
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
    """문제 폴더 update 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (ProblemFolderUpdateRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 폴더 update 데이터입니다.
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
    """문제 샘플 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

        Args:
            request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
            problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
            force (bool): 캐시나 기존 검사 결과를 무시하고 다시 실행할지 여부입니다.
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
