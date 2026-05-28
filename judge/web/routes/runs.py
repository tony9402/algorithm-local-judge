"""runs 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
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
    """api_run 함수를 실행하고 결과를 반환합니다.
    
    Args:
        http_request (Request): `http_request` 값입니다.
        request (RunRequest): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
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
    """api_run_upload 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (Annotated[str, Form()]): 문제 ID입니다.
        file (Annotated[UploadFile, File()]): 파일 경로 또는 파일 객체입니다.
        profile (Annotated[str | None, Form()]): `profile` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
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
    """api_run_stream 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (Annotated[str, Form()]): 문제 ID입니다.
        source_mode (Annotated[str, Form()]): `source_mode` 값입니다.
        profile (Annotated[str | None, Form()]): `profile` 값입니다.
        filename (Annotated[str | None, Form()]): `filename` 값입니다.
        source_text (Annotated[str | None, Form()]): `source_text` 값입니다.
        file (Annotated[UploadFile | None, File()]): 파일 경로 또는 파일 객체입니다.
    
    Returns:
        StreamingResponse: 처리 결과를 반환합니다.
    """
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
    """api_run_job 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (Annotated[str, Form()]): 문제 ID입니다.
        source_mode (Annotated[str, Form()]): `source_mode` 값입니다.
        profile (Annotated[str | None, Form()]): `profile` 값입니다.
        filename (Annotated[str | None, Form()]): `filename` 값입니다.
        source_text (Annotated[str | None, Form()]): `source_text` 값입니다.
        file (Annotated[UploadFile | None, File()]): 파일 경로 또는 파일 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
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
        """operation 함수를 실행하고 결과를 반환합니다.
        
        Args:
            cancel_token (Any): `cancel_token` 값입니다.
            progress (Any): `progress` 값입니다.
        
        Returns:
            Any: 처리 결과를 반환합니다.
        """
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
    """api_run_result 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_id (str): `run_id` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        return services.run_result(run_id)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/runs/{run_id}/wrong/{case_id}")
def api_wrong_case(run_id: str, case_id: str) -> dict:
    """api_wrong_case 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_id (str): `run_id` 값입니다.
        case_id (str): `case_id` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        return services.wrong_case(run_id, case_id)
    except Exception as exc:
        raise to_http_error(exc) from exc
