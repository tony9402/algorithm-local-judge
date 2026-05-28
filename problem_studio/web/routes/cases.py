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
    enqueue_background_job,
    jobs_from_request,
    route_result,
    scoped_lane,
    stream_operation,
    to_http_error,
    workspace_from_request,
)
from problem_studio.web.schemas import CasesCompileRequest, DataValidateRequest, GenerateRequest
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/problems/{problem_id}", tags=["cases"])


@router.post("/cases/compile")
def api_cases_compile(request: Request, problem_id: str, body: CasesCompileRequest) -> dict:
    """Compile cases.yml and return diagnostics."""

    def operation() -> dict:
        ensure_local_write_allowed(request, "case compilation")
        return compile_cases(workspace_from_request(request), problem_id, body.profile)

    return route_result(operation)


@router.post("/cases/jobs")
def api_cases_compile_job(request: Request, problem_id: str, body: CasesCompileRequest) -> dict:
    """Queue cases.yml compilation for one problem."""
    try:
        ensure_local_write_allowed(request, "case compilation")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)
        profile = body.profile

        def operation(cancel_token, progress):
            progress(f"Compiling cases.yml for {problem_id}.", label="Cases 검사")
            cancel_token.check()
            result = compile_cases(workspace, problem_id, profile)
            progress("cases.yml compile finished.", label="Cases 검사")
            return result

        job = enqueue_background_job(
            jobs,
            request=request,
            kind="cases-compile",
            title=f"Cases 검사 · {problem_id}",
            problem_id=problem_id,
            lane=scoped_lane(request, problem_id, "compile"),
            target={"problemId": problem_id, "profile": profile},
            operation=operation,
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/generate/stream")
def api_generate_stream(
    request: Request, problem_id: str, body: GenerateRequest
) -> StreamingResponse:
    """Generate test data with progress events."""
    try:
        ensure_local_write_allowed(request, "data generation")
        workspace = workspace_from_request(request)
    except Exception as exc:
        raise to_http_error(exc) from exc

    def operation(progress):
        return generate_profile_data(workspace, problem_id, body.profile, body.force, progress)

    return StreamingResponse(stream_operation(operation), media_type="text/event-stream")


@router.post("/generate/jobs")
def api_generate_job(request: Request, problem_id: str, body: GenerateRequest) -> dict:
    """Queue test data generation for one problem/profile."""
    try:
        ensure_local_write_allowed(request, "data generation")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
            progress(
                f"Generating {body.profile} data for {problem_id}.",
                label="데이터 생성",
            )
            result = generate_profile_data(
                workspace,
                problem_id,
                body.profile,
                body.force,
                progress,
            )
            cancel_token.check()
            return result

        job = enqueue_background_job(
            jobs,
            request=request,
            kind="data-generate",
            title=f"{body.profile} 데이터 생성 · {problem_id}",
            problem_id=problem_id,
            lane=scoped_lane(request, problem_id, "validation"),
            target={"problemId": problem_id, "profile": body.profile, "force": body.force},
            operation=operation,
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/validate/stream")
def api_validate_data_stream(
    request: Request, problem_id: str, body: DataValidateRequest
) -> StreamingResponse:
    """Generate and validate every cases.yml profile with progress events."""
    try:
        ensure_local_write_allowed(request, "data validation")
        workspace = workspace_from_request(request)
    except Exception as exc:
        raise to_http_error(exc) from exc

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


@router.post("/validate/jobs")
def api_validate_data_job(request: Request, problem_id: str, body: DataValidateRequest) -> dict:
    """Queue full data generation and validation for one problem."""
    try:
        ensure_local_write_allowed(request, "data validation")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
            progress(f"Validating generated data for {problem_id}.", label="데이터 벨리데이션")
            result = validate_all_data(
                workspace,
                problem_id,
                body.force,
                progress,
                prefix_profile_logs=True,
                include_labels=True,
            )
            cancel_token.check()
            return result

        job = enqueue_background_job(
            jobs,
            request=request,
            kind="data-validate",
            title=f"모든 데이터 생성+검증 · {problem_id}",
            problem_id=problem_id,
            lane=scoped_lane(request, problem_id, "validation"),
            target={"problemId": problem_id, "force": body.force},
            operation=operation,
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/samples")
def api_samples(request: Request, problem_id: str, force: bool = False) -> dict:
    """Generate and return visible sample cases."""

    def operation() -> dict:
        ensure_local_write_allowed(request, "sample generation")
        return sample_cases(workspace_from_request(request), problem_id, force)

    return route_result(operation)
