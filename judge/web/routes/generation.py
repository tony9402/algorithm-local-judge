from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from judge.web import services
from judge.web.routes.common import enqueue_background_job, jobs_from_request, to_http_error
from judge.web.schemas import CasesCompileRequest, GenerateRequest
from judge.web.security_policy import ensure_remote_run_allowed

router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/generate")
def api_generate(http_request: Request, request: GenerateRequest) -> dict:
    """Generate test data for one problem/profile."""
    try:
        ensure_remote_run_allowed(http_request)
        return services.generate_problem(request.problem_id, request.profile, request.force)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/generate/stream")
def api_generate_stream(http_request: Request, request: GenerateRequest) -> StreamingResponse:
    """Generate test data while streaming progress events."""
    try:
        ensure_remote_run_allowed(http_request)
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


@router.post("/generate/jobs")
def api_generate_job(http_request: Request, request: GenerateRequest) -> dict:
    """Queue test data generation for one problem/profile."""
    try:
        ensure_remote_run_allowed(http_request)
        jobs = jobs_from_request(http_request)

        def operation(cancel_token, progress):
            progress(
                f"Generating {request.profile or 'default'} data for {request.problem_id}.",
                label="Data generation",
            )
            result = services.generate_problem_with_progress(
                request.problem_id,
                request.profile,
                request.force,
                progress,
            )
            cancel_token.check()
            return result

        job = enqueue_background_job(
            jobs,
            kind="judge-generate",
            title=f"Generate Data · {request.problem_id}",
            problem_id=request.problem_id,
            lane=f"judge:{request.problem_id}:run",
            target={
                "problemId": request.problem_id,
                "profile": request.profile,
                "force": request.force,
            },
            operation=operation,
            result_actions={"apply": True},
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/cases/compile")
def api_cases_compile(request: CasesCompileRequest) -> dict:
    """Compile cases.yml and return diagnostics for one problem/profile."""
    try:
        return services.compile_problem_cases_result(request.problem_id, request.profile)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/cases/jobs")
def api_cases_compile_job(http_request: Request, request: CasesCompileRequest) -> dict:
    """Queue cases.yml compilation for one problem/profile."""
    try:
        ensure_remote_run_allowed(http_request)
        jobs = jobs_from_request(http_request)

        def operation(cancel_token, progress):
            progress(f"Compiling cases.yml for {request.problem_id}.", label="Cases compile")
            cancel_token.check()
            return services.compile_problem_cases_result(request.problem_id, request.profile)

        job = enqueue_background_job(
            jobs,
            kind="judge-cases-compile",
            title=f"Check Cases · {request.problem_id}",
            problem_id=request.problem_id,
            lane=f"judge:{request.problem_id}:compile",
            target={"problemId": request.problem_id, "profile": request.profile},
            operation=operation,
            result_actions={"apply": True},
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc
