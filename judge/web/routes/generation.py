"""생성 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from judge.web import services
from judge.web.routes.common import enqueue_background_job, jobs_from_request, to_http_error
from judge.web.schemas import CasesCompileRequest, GenerateRequest
from judge.web.security_policy import ensure_remote_run_allowed

router = APIRouter(prefix="/api", tags=["generation"])


def _cases_compile_failure_payload(result: dict) -> dict:
    if result.get("valid") is not False:
        result["passed"] = True
        return result
    diagnostics = result.get("diagnostics") or []
    first = diagnostics[0] if diagnostics and isinstance(diagnostics[0], dict) else {}
    target_parts = [
        first.get("path"),
        f"line {first.get('line')}" if first.get("line") else None,
        first.get("location"),
    ]
    target = " · ".join(str(part) for part in target_parts if part)
    message = str(first.get("message") or "cases.yml compile failed.")
    if first.get("hint"):
        message = f"{message} ({first['hint']})"
    result.update(
        {
            "passed": False,
            "errorKind": "cases-invalid",
            "failureStage": "cases",
            "failureStageLabel": "cases.yml 검사",
            "summary": message,
            "failureDetails": [
                {
                    "type": "cases-diagnostic",
                    "label": "cases.yml 검사",
                    "target": target or result.get("path") or "cases.yml",
                    "message": message,
                    "severity": first.get("severity"),
                    "profile": first.get("profile"),
                    "location": first.get("location"),
                    "line": first.get("line"),
                }
            ],
        }
    )
    return result


@router.post("/generate")
def api_generate(http_request: Request, request: GenerateRequest) -> dict:
    """generate 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        http_request (Request): 원격 실행 허용 여부를 판단할 FastAPI 요청 객체입니다.
        request (GenerateRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 generate 데이터입니다.
    """
    try:
        ensure_remote_run_allowed(http_request)
        return services.generate_problem(request.problem_id, request.profile, request.force)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/generate/stream")
def api_generate_stream(http_request: Request, request: GenerateRequest) -> StreamingResponse:
    """generate 스트림 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        http_request (Request): 원격 실행 허용 여부를 판단할 FastAPI 요청 객체입니다.
        request (GenerateRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        StreamingResponse: 브라우저가 진행 이벤트를 받을 수 있는 스트리밍 HTTP 응답입니다.
    """
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
    """generate 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        http_request (Request): 원격 실행 허용 여부를 판단할 FastAPI 요청 객체입니다.
        request (GenerateRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 generate 작업 데이터입니다.
    """
    try:
        ensure_remote_run_allowed(http_request)
        jobs = jobs_from_request(http_request)

        def operation(cancel_token, progress):
            progress(
                f"Generating {request.profile or 'default'} data for {request.problem_id}.",
                label="데이터 생성",
                failureStage="validation",
                failureStageLabel="데이터 생성",
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
    """케이스 컴파일 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (CasesCompileRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 케이스 컴파일 데이터입니다.
    """
    try:
        return services.compile_problem_cases_result(request.problem_id, request.profile)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/cases/jobs")
def api_cases_compile_job(http_request: Request, request: CasesCompileRequest) -> dict:
    """케이스 컴파일 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        http_request (Request): 원격 실행 허용 여부를 판단할 FastAPI 요청 객체입니다.
        request (CasesCompileRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 케이스 컴파일 작업 데이터입니다.
    """
    try:
        ensure_remote_run_allowed(http_request)
        jobs = jobs_from_request(http_request)

        def operation(cancel_token, progress):
            progress(
                f"Compiling cases.yml for {request.problem_id}.",
                label="cases.yml 검사",
                failureStage="cases",
                failureStageLabel="cases.yml 검사",
            )
            cancel_token.check()
            result = services.compile_problem_cases_result(request.problem_id, request.profile)
            return _cases_compile_failure_payload(result)

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
