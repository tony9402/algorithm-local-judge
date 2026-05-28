from __future__ import annotations

from fastapi import APIRouter, Request

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.security_policy import ensure_local_web_action_allowed

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def api_source_history() -> dict:
    """Return cached source files submitted through the web UI."""
    try:
        return services.list_source_history()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/{source_id}")
def api_source_history_detail(request: Request, source_id: str) -> dict:
    """Return one cached source file with source text."""
    try:
        ensure_local_web_action_allowed(request, "source history detail")
        return services.source_history_detail(source_id)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.delete("/{source_id}")
def api_source_history_delete(request: Request, source_id: str) -> dict:
    """Delete one cached source file."""
    try:
        ensure_local_web_action_allowed(request, "source history delete")
        return services.delete_source_history(source_id)
    except Exception as exc:
        raise to_http_error(exc) from exc
