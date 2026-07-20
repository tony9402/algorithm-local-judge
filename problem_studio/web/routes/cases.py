"""케이스 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다."""

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
from problem_studio.web.security_policy import (
    ensure_local_web_action_allowed,
    ensure_local_write_allowed,
)

router = APIRouter(prefix="/api/problems/{problem_id}", tags=["cases"])


@router.post("/cases/compile")
def api_cases_compile(request: Request, problem_id: str, body: CasesCompileRequest) -> dict:
    """케이스 컴파일 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (CasesCompileRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 케이스 컴파일 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "case compilation")
        return compile_cases(workspace_from_request(request), problem_id, body.profile)

    return route_result(operation)


@router.post("/cases/jobs")
def api_cases_compile_job(request: Request, problem_id: str, body: CasesCompileRequest) -> dict:
    """케이스 컴파일 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (CasesCompileRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 케이스 컴파일 작업 데이터입니다.
    """
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
    """generate 스트림 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (GenerateRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        StreamingResponse: 브라우저가 진행 이벤트를 받을 수 있는 스트리밍 HTTP 응답입니다.
    """
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
    """generate 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (GenerateRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 generate 작업 데이터입니다.
    """
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
    """데이터 스트림 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (DataValidateRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        StreamingResponse: 브라우저가 진행 이벤트를 받을 수 있는 스트리밍 HTTP 응답입니다.
    """
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
    """데이터 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (DataValidateRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 데이터 작업 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "data validation")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
            progress(f"Validating generated data for {problem_id}.", label="데이터 검증")
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
    """샘플 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        force (bool): 캐시나 기존 검사 결과를 무시하고 다시 실행할지 여부입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 샘플 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_web_action_allowed(request, "sample read")
        return sample_cases(workspace_from_request(request), problem_id, force)

    return route_result(operation)
