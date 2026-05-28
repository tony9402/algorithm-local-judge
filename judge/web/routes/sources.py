"""소스 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.security_policy import ensure_local_web_action_allowed

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def api_source_history() -> dict:
    """소스 이력 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 소스 이력 데이터입니다.
    """
    try:
        return services.list_source_history()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/{source_id}")
def api_source_history_detail(request: Request, source_id: str) -> dict:
    """소스 이력 detail 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        source_id (str): 소스 ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 소스 이력 detail 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(request, "source history detail")
        return services.source_history_detail(source_id)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.delete("/{source_id}")
def api_source_history_delete(request: Request, source_id: str) -> dict:
    """소스 이력 delete 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        source_id (str): 소스 ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 소스 이력 delete 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(request, "source history delete")
        return services.delete_source_history(source_id)
    except Exception as exc:
        raise to_http_error(exc) from exc
