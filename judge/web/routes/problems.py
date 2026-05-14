from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from judge.web import services
from judge.web.routes.common import etag_matches, to_http_error

router = APIRouter(prefix="/api", tags=["problems"])


@router.get("/problems")
def api_problems() -> list[dict]:
    """Return discovered problems."""
    try:
        return services.list_problems()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/problems/{problem_id}/samples")
def api_problem_samples(
    request: Request,
    problem_id: str,
    force: bool = Query(default=False),
) -> Response:
    """Return sample input and expected output for a problem."""
    try:
        result = services.sample_cases(problem_id, force)
        etag = str(result.get("etag", ""))
        headers = {"Cache-Control": "private, max-age=0, must-revalidate"}
        if etag:
            headers["ETag"] = etag
        if not force and etag_matches(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)
        return JSONResponse(result, headers=headers)
    except Exception as exc:
        raise to_http_error(exc) from exc
