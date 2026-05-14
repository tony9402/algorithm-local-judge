from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.schemas import CasesCompileRequest, GenerateRequest

router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/generate")
def api_generate(request: GenerateRequest) -> dict:
    """Generate test data for one problem/profile."""
    try:
        return services.generate_problem(request.problem_id, request.profile, request.force)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/generate/stream")
def api_generate_stream(request: GenerateRequest) -> StreamingResponse:
    """Generate test data while streaming progress events."""
    try:
        return StreamingResponse(
            services.generate_problem_events(
                request.problem_id,
                request.profile,
                request.force,
            ),
            media_type="text/event-stream",
        )
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/cases/compile")
def api_cases_compile(request: CasesCompileRequest) -> dict:
    """Compile cases.yml and return diagnostics for one problem/profile."""
    try:
        return services.compile_problem_cases_result(request.problem_id, request.profile)
    except Exception as exc:
        raise to_http_error(exc) from exc
