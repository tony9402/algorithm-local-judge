"""sources 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.security_policy import ensure_local_web_action_allowed

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def api_source_history() -> dict:
    """api_source_history 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        return services.list_source_history()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/{source_id}")
def api_source_history_detail(request: Request, source_id: str) -> dict:
    """api_source_history_detail 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        source_id (str): 소스 ID입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        ensure_local_web_action_allowed(request, "source history detail")
        return services.source_history_detail(source_id)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.delete("/{source_id}")
def api_source_history_delete(request: Request, source_id: str) -> dict:
    """api_source_history_delete 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        source_id (str): 소스 ID입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        ensure_local_web_action_allowed(request, "source history delete")
        return services.delete_source_history(source_id)
    except Exception as exc:
        raise to_http_error(exc) from exc
