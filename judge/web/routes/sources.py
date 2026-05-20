from __future__ import annotations

from fastapi import APIRouter

from judge.web import services
from judge.web.routes.common import to_http_error

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def api_source_history() -> dict:
    """Return cached source files submitted through the web UI."""
    try:
        return services.list_source_history()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/{source_id}")
def api_source_history_detail(source_id: str) -> dict:
    """Return one cached source file with source text."""
    try:
        return services.source_history_detail(source_id)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.delete("/{source_id}")
def api_source_history_delete(source_id: str) -> dict:
    """Delete one cached source file."""
    try:
        return services.delete_source_history(source_id)
    except Exception as exc:
        raise to_http_error(exc) from exc
