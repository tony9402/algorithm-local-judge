"""솔루션 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse

from alj_core.artifacts import wrong_artifacts, wrong_diff_text
from problem_studio.core.editor import (
    create_solution_file,
    delete_solution_file,
    list_problem_files,
    rename_solution_file,
    save_solution_upload,
)
from problem_studio.core.packflow import list_solutions, verify_solutions
from problem_studio.core.stress import (
    append_stress_case,
    stress_mismatch_preview,
    stress_test_solutions,
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
from problem_studio.web.schemas import (
    SolutionCreateRequest,
    SolutionDeleteRequest,
    SolutionRenameRequest,
    SolutionStressRequest,
    SolutionTestRequest,
    SolutionVerifyRequest,
    StressAppendRequest,
)
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/problems/{problem_id}/solutions", tags=["solutions"])
ARTIFACT_PREVIEW_LIMIT = 12000
DEFAULT_SOLUTION_VERIFY_WORKERS = 4


def preview_artifact_text(text: str, limit: int = ARTIFACT_PREVIEW_LIMIT) -> dict:
    """미리보기 산출물 텍스트 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        text (str): 화면에 표시하거나 비교에 사용할 텍스트입니다.
        limit (int): 미리보기 산출물 텍스트을 계산하거나 검증할 때 필요한 제한 입력입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 미리보기 산출물 텍스트 데이터입니다.
    """
    if len(text) <= limit:
        return {"text": text, "truncated": False, "omittedChars": 0}
    omitted = len(text) - limit
    preview = text[:limit].rstrip()
    preview += f"\n\n... truncated after {limit} chars, omitted {omitted} chars ..."
    return {"text": preview, "truncated": True, "omittedChars": omitted}


@router.get("")
def api_solutions(request: Request, problem_id: str) -> dict:
    """솔루션 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 데이터입니다.
    """
    return route_result(
        lambda: {"solutions": list_solutions(workspace_from_request(request), problem_id)}
    )


@router.post("/upload")
async def api_solutions_upload(
    request: Request,
    problem_id: str,
    files: Annotated[list[UploadFile], File(...)],
) -> dict:
    """솔루션 업로드 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        files (Annotated[list[UploadFile], File(...)]): 솔루션 업로드을 계산하거나 검증할 때 필요한 파일 입력입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 업로드 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "solution upload")
        workspace = workspace_from_request(request)
        uploaded = []
        for file in files:
            uploaded.append(
                save_solution_upload(
                    workspace,
                    problem_id,
                    file.filename or "",
                    await file.read(),
                )
            )
        return {
            "uploaded": uploaded,
            "files": list_problem_files(workspace, problem_id),
            "solutions": list_solutions(workspace, problem_id),
        }
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/create")
def api_solutions_create(request: Request, problem_id: str, body: SolutionCreateRequest) -> dict:
    """솔루션 create 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (SolutionCreateRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 create 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "solution creation")
        workspace = workspace_from_request(request)
        created = create_solution_file(
            workspace,
            problem_id,
            body.name,
            body.expected,
            body.language,
        )
        return {
            "created": created,
            "files": list_problem_files(workspace, problem_id),
            "solutions": list_solutions(workspace, problem_id),
        }

    return route_result(operation)


@router.patch("/rename")
def api_solutions_rename(request: Request, problem_id: str, body: SolutionRenameRequest) -> dict:
    """솔루션 rename 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (SolutionRenameRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 rename 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "solution rename")
        workspace = workspace_from_request(request)
        renamed = rename_solution_file(
            workspace,
            problem_id,
            body.path,
            body.name,
            body.expected,
            body.language,
        )
        return {
            "renamed": {"path": renamed["path"], "size": renamed["size"]},
            "metadata": renamed["metadata"],
            "files": list_problem_files(workspace, problem_id),
            "solutions": list_solutions(workspace, problem_id),
        }

    return route_result(operation)


@router.delete("")
def api_solutions_delete(request: Request, problem_id: str, body: SolutionDeleteRequest) -> dict:
    """솔루션 delete 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (SolutionDeleteRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 delete 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "solution delete")
        workspace = workspace_from_request(request)
        deleted = delete_solution_file(workspace, problem_id, body.path)
        return {
            **deleted,
            "files": list_problem_files(workspace, problem_id),
            "solutions": list_solutions(workspace, problem_id),
        }

    return route_result(operation)


@router.post("/verify/stream")
def api_solutions_verify_stream(
    request: Request, problem_id: str, body: SolutionVerifyRequest
) -> StreamingResponse:
    """솔루션 verify 스트림 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (SolutionVerifyRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        StreamingResponse: 브라우저가 진행 이벤트를 받을 수 있는 스트리밍 HTTP 응답입니다.
    """
    try:
        ensure_local_write_allowed(request, "solution verification")
        workspace = workspace_from_request(request)
    except Exception as exc:
        raise to_http_error(exc) from exc

    def operation(progress):
        progress(f"Verifying solutions for {problem_id} on profile {body.profile}.")
        result = verify_solutions(
            workspace,
            problem_id,
            body.profile,
            progress=progress,
            raise_on_failure=False,
            max_workers=body.max_workers or DEFAULT_SOLUTION_VERIFY_WORKERS,
        )
        result = {**result, "scope": "all"}
        progress(
            "Solution expectation verification finished."
            if result.get("passed")
            else "Solution expectation verification finished with mismatches."
        )
        return result

    return StreamingResponse(stream_operation(operation), media_type="text/event-stream")


@router.post("/verify/jobs")
def api_solutions_verify_job(
    request: Request, problem_id: str, body: SolutionVerifyRequest
) -> dict:
    """솔루션 verify 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (SolutionVerifyRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 verify 작업 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "solution verification")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)
        worker_count = body.max_workers or DEFAULT_SOLUTION_VERIFY_WORKERS

        def operation(cancel_token, progress):
            progress(f"Verifying solutions for {problem_id} on profile {body.profile}.")
            summary = {"verifiedCount": 0, "failedCount": 0}

            def on_check(check, index: int, total: int) -> None:
                payload = check.to_dict(workspace)
                summary["verifiedCount"] = index
                if not check.passed:
                    summary["failedCount"] += 1
                progress(
                    f"{payload['source']} verified: {payload['actualStatus']}",
                    current=index,
                    total=total,
                    label="솔루션 기대 결과 검증",
                    partialCheck=payload,
                    partialSummary={
                        **summary,
                        "totalCount": total,
                        "maxWorkers": worker_count,
                    },
                )

            result = verify_solutions(
                workspace,
                problem_id,
                body.profile,
                progress=progress,
                raise_on_failure=False,
                on_check=on_check,
                max_workers=worker_count,
                cancel_check=cancel_token.check,
            )
            result = {**result, "scope": "all"}
            cancel_token.check()
            progress(
                "Solution expectation verification finished."
                if result.get("passed")
                else "Solution expectation verification finished with mismatches."
            )
            return result

        job = enqueue_background_job(
            jobs,
            request=request,
            kind="solution-verify",
            title=f"기대 결과 검증 · {problem_id}",
            problem_id=problem_id,
            lane=scoped_lane(request, problem_id, "validation"),
            target={
                "problemId": problem_id,
                "profile": body.profile,
                "scope": "all",
                "maxWorkers": worker_count,
            },
            operation=operation,
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/test/jobs")
def api_solution_test_job(
    request: Request, problem_id: str, body: SolutionTestRequest
) -> dict:
    """솔루션 개별 테스트 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (SolutionTestRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 개별 테스트 작업 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "solution single test")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
            progress(
                f"Testing solution {body.solution} for {problem_id} on profile {body.profile}."
            )

            def on_check(check, index: int, total: int) -> None:
                payload = check.to_dict(workspace)
                progress(
                    f"{payload['source']} tested: {payload['actualStatus']}",
                    current=index,
                    total=total,
                    label="개별 테스트",
                    partialCheck=payload,
                    partialSummary={
                        "verifiedCount": index,
                        "failedCount": 0 if check.passed else 1,
                        "totalCount": total,
                    },
                )

            result = verify_solutions(
                workspace,
                problem_id,
                body.profile,
                progress=progress,
                raise_on_failure=False,
                solutions=[body.solution],
                on_check=on_check,
                max_workers=1,
                cancel_check=cancel_token.check,
            )
            cancel_token.check()
            progress(
                "Single solution test finished."
                if result.get("passed")
                else "Single solution test finished with mismatches."
            )
            return {**result, "scope": "single", "solution": body.solution}

        job = enqueue_background_job(
            jobs,
            request=request,
            kind="solution-test",
            title=f"개별 테스트 · {problem_id}",
            problem_id=problem_id,
            lane=scoped_lane(request, problem_id, "validation"),
            target={
                "problemId": problem_id,
                "profile": body.profile,
                "solution": body.solution,
                "scope": "single",
            },
            operation=operation,
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/stress/jobs")
def api_solutions_stress_job(
    request: Request, problem_id: str, body: SolutionStressRequest
) -> dict:
    """솔루션 스트레스 테스트 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (SolutionStressRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 스트레스 테스트 작업 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "solution stress test")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
            result = stress_test_solutions(
                workspace,
                problem_id,
                body.profile,
                duration_seconds=body.duration_seconds,
                max_cases=body.max_cases,
                solutions=body.solutions,
                stop_on_first_mismatch=body.stop_on_first_mismatch,
                cancel_token=cancel_token,
                progress=progress,
            )
            cancel_token.check()
            return result

        job = enqueue_background_job(
            jobs,
            request=request,
            kind="solution-stress",
            title=f"Stress 테스트 · {problem_id}",
            problem_id=problem_id,
            lane=scoped_lane(request, problem_id, "validation"),
            target={
                "problemId": problem_id,
                "profile": body.profile,
                "durationSeconds": min(300, max(1, body.duration_seconds)),
                "maxCases": body.max_cases,
                "solutions": body.solutions,
                "stopOnFirstMismatch": body.stop_on_first_mismatch,
            },
            operation=operation,
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/runs/{run_id}/wrong/{case_id}")
def api_solution_wrong_case(
    request: Request,
    problem_id: str,
    run_id: str,
    case_id: str,
) -> dict:
    """솔루션 오답 케이스 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        run_id (str): 저장된 실행 결과와 산출물 디렉터리를 찾는 실행 ID입니다.
        case_id (str): 입력, 출력, 오답 산출물을 구분하는 케이스 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 오답 케이스 데이터입니다.
    """
    try:
        workspace = workspace_from_request(request)
        raw_data = wrong_artifacts(run_id, case_id, workspace)
        raw_data["diff"] = wrong_diff_text(run_id, case_id, workspace)
        result = {
            "problemId": problem_id,
            "previewLimit": ARTIFACT_PREVIEW_LIMIT,
            "truncation": {},
        }
        for key, value in raw_data.items():
            preview = preview_artifact_text(value)
            result[key] = preview["text"]
            result["truncation"][key] = {
                "truncated": preview["truncated"],
                "omittedChars": preview["omittedChars"],
            }
        return result
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/stress/runs/{run_id}/mismatches/{case_id}/{solution_key}")
def api_solution_stress_mismatch(
    request: Request,
    problem_id: str,
    run_id: str,
    case_id: str,
    solution_key: str,
) -> dict:
    """솔루션 스트레스 테스트 mismatch 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        run_id (str): 저장된 실행 결과와 산출물 디렉터리를 찾는 실행 ID입니다.
        case_id (str): 입력, 출력, 오답 산출물을 구분하는 케이스 ID입니다.
        solution_key (str): 솔루션 스트레스 테스트 mismatch을 계산하거나 검증할 때 필요한 솔루션 key 입력입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 스트레스 테스트 mismatch 데이터입니다.
    """
    try:
        workspace = workspace_from_request(request)
        result = stress_mismatch_preview(
            workspace,
            run_id,
            case_id,
            solution_key,
            limit=ARTIFACT_PREVIEW_LIMIT,
        )
        return {"problemId": problem_id, **result}
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/stress/runs/{run_id}/mismatches/{case_id}/{solution_key}/append")
def api_solution_stress_append(
    request: Request,
    problem_id: str,
    run_id: str,
    case_id: str,
    solution_key: str,
    body: StressAppendRequest,
) -> dict:
    """솔루션 스트레스 테스트 append 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        run_id (str): 저장된 실행 결과와 산출물 디렉터리를 찾는 실행 ID입니다.
        case_id (str): 입력, 출력, 오답 산출물을 구분하는 케이스 ID입니다.
        solution_key (str): 솔루션 스트레스 테스트 append을 계산하거나 검증할 때 필요한 솔루션 key 입력입니다.
        body (StressAppendRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 스트레스 테스트 append 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "append stress case")
        workspace = workspace_from_request(request)
        result = append_stress_case(
            workspace,
            problem_id,
            body.profile,
            run_id,
            case_id,
            solution_key,
            mode=body.mode,
            name=body.name,
        )
        return {
            **result,
            "files": list_problem_files(workspace, problem_id),
            "solutions": list_solutions(workspace, problem_id),
        }
    except Exception as exc:
        raise to_http_error(exc) from exc
