from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from problem_studio.core.validation import (
    compile_cases,
    generate_profile_data,
    sample_cases,
    validate_all_data,
)
from problem_studio.web.routes.common import (
    route_result,
    stream_operation,
    workspace_from_request,
)
from problem_studio.web.schemas import CasesCompileRequest, DataValidateRequest, GenerateRequest

router = APIRouter(prefix="/api/problems/{problem_id}", tags=["cases"])


@router.post("/cases/compile")
def api_cases_compile(request: Request, problem_id: str, body: CasesCompileRequest) -> dict:
    """Compile cases.yml and return diagnostics."""
    return route_result(
        lambda: compile_cases(workspace_from_request(request), problem_id, body.profile)
    )


@router.post("/generate/stream")
def api_generate_stream(
    request: Request, problem_id: str, body: GenerateRequest
) -> StreamingResponse:
    """Generate test data with progress events."""
    workspace = workspace_from_request(request)

    def operation(progress):
        return generate_profile_data(workspace, problem_id, body.profile, body.force, progress)

    return StreamingResponse(stream_operation(operation), media_type="text/event-stream")


@router.post("/validate/stream")
def api_validate_data_stream(
    request: Request, problem_id: str, body: DataValidateRequest
) -> StreamingResponse:
    """Generate and validate every cases.yml profile with progress events."""
    workspace = workspace_from_request(request)

    def operation(progress):
        return validate_all_data(
            workspace,
            problem_id,
            body.force,
            progress,
            prefix_profile_logs=True,
            include_labels=True,
        )

    return StreamingResponse(stream_operation(operation), media_type="text/event-stream")


@router.get("/samples")
def api_samples(request: Request, problem_id: str, force: bool = False) -> dict:
    """Generate and return visible sample cases."""
    return route_result(lambda: sample_cases(workspace_from_request(request), problem_id, force))
