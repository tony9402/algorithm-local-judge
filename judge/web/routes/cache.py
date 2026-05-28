"""캐시 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.schemas import CacheClearRequest
from judge.web.security_policy import ensure_local_web_action_allowed

router = APIRouter(prefix="/api/cache", tags=["cache"])


@router.get("")
def api_cache() -> dict:
    """캐시 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 캐시 데이터입니다.
    """
    try:
        return services.cache_status()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/clear")
def api_cache_clear(http_request: Request, request: CacheClearRequest) -> dict:
    """캐시 clear 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        http_request (Request): 원격 실행 허용 여부를 판단할 FastAPI 요청 객체입니다.
        request (CacheClearRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 캐시 clear 데이터입니다.
    """
    try:
        if not request.dry_run:
            ensure_local_web_action_allowed(http_request, "cache clear")
        return services.cache_clear(
            request.problem,
            request.profile,
            request.runs,
            request.all_entries,
            request.dry_run,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc
