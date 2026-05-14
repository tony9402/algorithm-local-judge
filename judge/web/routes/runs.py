from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.schemas import RunRequest

router = APIRouter(prefix="/api", tags=["runs"])


@router.post("/run")
def api_run(request: RunRequest) -> dict:
    """Judge a local path or pasted source code."""
    try:
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
    problem_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    profile: Annotated[str | None, Form()] = None,
) -> dict:
    """Judge an uploaded source file and return the final result."""
    try:
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
    problem_id: Annotated[str, Form()],
    source_mode: Annotated[str, Form()],
    profile: Annotated[str | None, Form()] = None,
    filename: Annotated[str | None, Form()] = None,
    source_text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> StreamingResponse:
    """Judge an uploaded source file or pasted code with live progress events."""
    try:
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
