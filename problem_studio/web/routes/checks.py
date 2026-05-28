"""checks 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from judge.core.compiler import compile_problem_tools
from problem_studio.core.packflow import verify_solutions
from problem_studio.core.validation import compile_cases, validate_all_data
from problem_studio.web.routes.common import (
    enqueue_background_job,
    jobs_from_request,
    scoped_lane,
    to_http_error,
    workspace_from_request,
)
from problem_studio.web.schemas import DataValidateRequest
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/problems/{problem_id}/checks", tags=["checks"])


@router.post("/jobs")
def api_run_all_checks_job(
    request: Request,
    problem_id: str,
    body: DataValidateRequest | None = None,
) -> dict:
    """api_run_all_checks_job 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        problem_id (str): 문제 ID입니다.
        body (DataValidateRequest | None): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        ensure_local_write_allowed(request, "full problem check")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)
        force = True if body is None else body.force

        def operation(cancel_token, progress):
        """operation 함수를 실행하고 결과를 반환합니다.
        
        Args:
            cancel_token (Any): `cancel_token` 값입니다.
            progress (Any): `progress` 값입니다.
        
        Returns:
            Any: 처리 결과를 반환합니다.
        """
            progress("Compiling cases.yml.", current=1, total=4, label="cases.yml 검사")
            cases = compile_cases(workspace, problem_id, None)
            cancel_token.check()
            progress("Compiling problem tools.", current=2, total=4, label="도구 컴파일")
            tools = compile_problem_tools(problem_id, workspace, progress=progress)
            cancel_token.check()
            progress(
                "Generating and validating all data.",
                current=3,
                total=4,
                label="데이터 검증",
            )
            validation = validate_all_data(
                workspace,
                problem_id,
                force,
                progress,
                prefix_profile_logs=True,
                include_labels=True,
            )
            cancel_token.check()
            progress(
                "Verifying expected-result solutions.",
                current=4,
                total=4,
                label="솔루션 검증",
            )
            verification = verify_solutions(
                workspace,
                problem_id,
                "hidden",
                progress=progress,
                raise_on_failure=False,
            )
            cancel_token.check()
            return {
                "problemId": problem_id,
                "passed": bool(verification.get("passed")),
                "cases": cases,
                "tools": {"labels": {name: str(path) for name, path in tools.items()}},
                "validation": validation,
                "verification": verification,
            }

        job = enqueue_background_job(
            jobs,
            request=request,
            kind="full-check",
            title=f"전체 테스트 · {problem_id}",
            problem_id=problem_id,
            lane=scoped_lane(request, problem_id, "validation"),
            target={"problemId": problem_id, "force": force},
            operation=operation,
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc
