from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from judge.web import services
from judge.web.routes.common import enqueue_background_job, jobs_from_request, to_http_error
from judge.web.schemas import RunRequest
from judge.web.security_policy import ensure_remote_run_allowed

router = APIRouter(prefix="/api", tags=["runs"])


@router.post("/run")
def api_run(http_request: Request, request: RunRequest) -> dict:
    """Judge a local path or pasted source code."""
    try:
        ensure_remote_run_allowed(http_request)
        return services.run_problem(
            request.problem_id,
            request.profile,
            request.source_mode,
            request.source_path,
            request.source_text,
            request.filename,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/run/upload")
def api_run_upload(
    request: Request,
    problem_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    profile: Annotated[str | None, Form()] = None,
) -> dict:
    """Judge an uploaded source file and return the final result."""
    try:
        ensure_remote_run_allowed(request)
        return services.run_uploaded_problem(
            problem_id,
            profile or None,
            file.file,
            file.filename,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/run/stream")
def api_run_stream(
    request: Request,
    problem_id: Annotated[str, Form()],
    source_mode: Annotated[str, Form()],
    profile: Annotated[str | None, Form()] = None,
    filename: Annotated[str | None, Form()] = None,
    source_text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> StreamingResponse:
    """Judge an uploaded source file or pasted code with live progress events."""
    try:
        ensure_remote_run_allowed(request)
        source = services.save_source_for_stream(
            source_mode,
            file.file if file is not None else None,
            file.filename if file is not None else None,
            source_text,
            filename,
            problem_id,
        )
        return StreamingResponse(
            services.run_problem_events(problem_id, profile or None, source),
            media_type="text/event-stream",
        )
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/run/jobs")
def api_run_job(
    request: Request,
    problem_id: Annotated[str, Form()],
    source_mode: Annotated[str, Form()],
    profile: Annotated[str | None, Form()] = None,
    filename: Annotated[str | None, Form()] = None,
    source_text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> dict:
    """Queue an uploaded or pasted source run."""
    try:
        ensure_remote_run_allowed(request)
        source = services.save_source_for_stream(
            source_mode,
            file.file if file is not None else None,
            file.filename if file is not None else None,
            source_text,
            filename,
            problem_id,
        )
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
            progress("Starting judge run.", label="Run Tests")
            result = services.run_problem_source_with_progress(
                problem_id,
                profile or None,
                source,
                progress,
            )
            cancel_token.check()
            return result

        job = enqueue_background_job(
            jobs,
            kind="judge-run",
            title=f"Run Tests · {problem_id}",
            problem_id=problem_id,
            lane=f"judge:{problem_id}:run",
            target={
                "problemId": problem_id,
                "profile": profile,
                "source": source.name,
                "sourceMode": source_mode,
            },
            operation=operation,
            result_actions={"apply": True},
            input_snapshot_summary=source.name,
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/runs/{run_id}")
def api_run_result(run_id: str) -> dict:
    """Return one saved run result."""
    try:
        return services.run_result(run_id)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/runs/{run_id}/wrong/{case_id}")
def api_wrong_case(run_id: str, case_id: str) -> dict:
    """Return wrong-answer artifact text and diff."""
    try:
        return services.wrong_case(run_id, case_id)
    except Exception as exc:
        raise to_http_error(exc) from exc
