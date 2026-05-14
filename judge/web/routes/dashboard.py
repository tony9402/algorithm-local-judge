from __future__ import annotations

from fastapi import APIRouter

from judge.web import services
from judge.web.routes.common import to_http_error

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/status")
def api_status() -> dict:
    """Return dashboard status."""
    try:
        return services.dashboard_status()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/config")
def api_config() -> dict:
    """Return lightweight web configuration."""
    try:
        return services.current_web_config()
    except Exception as exc:
        raise to_http_error(exc) from exc
