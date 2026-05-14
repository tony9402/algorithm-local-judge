from __future__ import annotations

from fastapi import APIRouter

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.schemas import CacheClearRequest

router = APIRouter(prefix="/api/cache", tags=["cache"])


@router.get("")
def api_cache() -> dict:
    """Return cache status."""
    try:
        return services.cache_status()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/clear")
def api_cache_clear(request: CacheClearRequest) -> dict:
    """Preview or apply a cache clear request."""
    try:
        return services.cache_clear(
            request.problem,
            request.profile,
            request.runs,
            request.all_entries,
            request.dry_run,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc
