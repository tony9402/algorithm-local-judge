"""cases 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
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
    """api_cases_compile 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (CasesCompileRequest): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """

    def operation() -> dict:
    """operation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
        ensure_local_write_allowed(request, "case compilation")
        return compile_cases(workspace_from_request(request), problem_id, body.profile)

    return route_result(operation)


@router.post("/cases/jobs")
def api_cases_compile_job(request: Request, problem_id: str, body: CasesCompileRequest) -> dict:
    """api_cases_compile_job 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (CasesCompileRequest): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        ensure_local_write_allowed(request, "case compilation")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)
        profile = body.profile

        def operation(cancel_token, progress):
        """operation 함수를 실행하고 결과를 반환합니다.
        
        Args:
            cancel_token (Any): `cancel_token` 값입니다.
            progress (Any): `progress` 값입니다.
        
        Returns:
            Any: 처리 결과를 반환합니다.
        """
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
    """api_generate_stream 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (GenerateRequest): `body` 값입니다.
    
    Returns:
        StreamingResponse: 처리 결과를 반환합니다.
    """
    try:
        ensure_local_write_allowed(request, "data generation")
        workspace = workspace_from_request(request)
    except Exception as exc:
        raise to_http_error(exc) from exc

    def operation(progress):
    """operation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        progress (Any): `progress` 값입니다.
    
    Returns:
        Any: 처리 결과를 반환합니다.
    """
        return generate_profile_data(workspace, problem_id, body.profile, body.force, progress)

    return StreamingResponse(stream_operation(operation), media_type="text/event-stream")


@router.post("/generate/jobs")
def api_generate_job(request: Request, problem_id: str, body: GenerateRequest) -> dict:
    """api_generate_job 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (GenerateRequest): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        ensure_local_write_allowed(request, "data generation")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
        """operation 함수를 실행하고 결과를 반환합니다.
        
        Args:
            cancel_token (Any): `cancel_token` 값입니다.
            progress (Any): `progress` 값입니다.
        
        Returns:
            Any: 처리 결과를 반환합니다.
        """
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
    """api_validate_data_stream 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (DataValidateRequest): `body` 값입니다.
    
    Returns:
        StreamingResponse: 처리 결과를 반환합니다.
    """
    try:
        ensure_local_write_allowed(request, "data validation")
        workspace = workspace_from_request(request)
    except Exception as exc:
        raise to_http_error(exc) from exc

    def operation(progress):
    """operation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        progress (Any): `progress` 값입니다.
    
    Returns:
        Any: 처리 결과를 반환합니다.
    """
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
    """api_validate_data_job 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (DataValidateRequest): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        ensure_local_write_allowed(request, "data validation")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
        """operation 함수를 실행하고 결과를 반환합니다.
        
        Args:
            cancel_token (Any): `cancel_token` 값입니다.
            progress (Any): `progress` 값입니다.
        
        Returns:
            Any: 처리 결과를 반환합니다.
        """
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
    """api_samples 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        force (bool): `force` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """

    def operation() -> dict:
    """operation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
        ensure_local_write_allowed(request, "sample generation")
        return sample_cases(workspace_from_request(request), problem_id, force)

    return route_result(operation)
