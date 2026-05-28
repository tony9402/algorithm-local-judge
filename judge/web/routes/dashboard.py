"""dashboard 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.security_policy import web_security_status

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/status")
def api_status(request: Request) -> dict:
    """api_status 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        status = services.dashboard_status()
        status["security"] = web_security_status(request)
        status["config"] = {**status["config"], "security": status["security"]}
        return status
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/config")
def api_config(request: Request) -> dict:
    """api_config 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        return {**services.current_web_config(), "security": web_security_status(request)}
    except Exception as exc:
        raise to_http_error(exc) from exc
