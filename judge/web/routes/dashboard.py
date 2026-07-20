"""대시보드 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다."""

from __future__ import annotations

from fastapi import APIRouter, Request

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.security_policy import web_security_status

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/status")
def api_status(request: Request) -> dict:
    """상태 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 상태 데이터입니다.
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
    """설정 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 설정 데이터입니다.
    """
    try:
        return {**services.current_web_config(), "security": web_security_status(request)}
    except Exception as exc:
        raise to_http_error(exc) from exc
