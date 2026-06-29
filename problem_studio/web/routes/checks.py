"""검사 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from alj_core.compiler import compile_problem_tools
from problem_studio.core.diagnostics import verification_failure_payload
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
DEFAULT_FULL_CHECK_SOLUTION_WORKERS = 4


@router.post("/jobs")
def api_run_all_checks_job(
    request: Request,
    problem_id: str,
    body: DataValidateRequest | None = None,
) -> dict:
    """all 검사 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (DataValidateRequest | None): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 all 검사 작업 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "full problem check")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)
        force = True if body is None else body.force

        def operation(cancel_token, progress):
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
            summary = {"verifiedCount": 0, "failedCount": 0}

            def on_check(check, index: int, total: int) -> None:
                payload = check.to_dict(workspace)
                summary["verifiedCount"] = index
                if not check.passed:
                    summary["failedCount"] += 1
                progress(
                    f"{payload['source']} verified: {payload['actualStatus']}",
                    current=4,
                    total=4,
                    label="솔루션 검증",
                    partialCheck=payload,
                    partialSummary={
                        **summary,
                        "totalCount": total,
                        "maxWorkers": DEFAULT_FULL_CHECK_SOLUTION_WORKERS,
                    },
                )

            verification = verify_solutions(
                workspace,
                problem_id,
                "hidden",
                progress=progress,
                raise_on_failure=False,
                on_check=on_check,
                max_workers=DEFAULT_FULL_CHECK_SOLUTION_WORKERS,
                cancel_check=cancel_token.check,
            )
            cancel_token.check()
            failure_payload = verification_failure_payload(verification)
            return {
                "problemId": problem_id,
                "passed": bool(verification.get("passed")),
                "cases": cases,
                "tools": {"labels": {name: str(path) for name, path in tools.items()}},
                "validation": validation,
                "verification": verification,
                **failure_payload,
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
