from __future__ import annotations

from fastapi import APIRouter, Request

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.security_policy import web_security_status

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/status")
def api_status(request: Request) -> dict:
    """Return dashboard status."""
    try:
        status = services.dashboard_status()
        status["security"] = web_security_status(request)
        status["config"] = {**status["config"], "security": status["security"]}
        return status
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/config")
def api_config(request: Request) -> dict:
    """Return lightweight web configuration."""
    try:
        return {**services.current_web_config(), "security": web_security_status(request)}
    except Exception as exc:
        raise to_http_error(exc) from exc
