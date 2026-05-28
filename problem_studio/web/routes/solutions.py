from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse

from judge.core.artifacts import wrong_artifacts, wrong_diff_text
from problem_studio.core.editor import (
    create_solution_file,
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
    StressAppendRequest,
    SolutionCreateRequest,
    SolutionRenameRequest,
    SolutionStressRequest,
    SolutionVerifyRequest,
)
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/problems/{problem_id}/solutions", tags=["solutions"])
ARTIFACT_PREVIEW_LIMIT = 12000


def preview_artifact_text(text: str, limit: int = ARTIFACT_PREVIEW_LIMIT) -> dict:
    """Return display-safe artifact preview text and truncation metadata."""
    if len(text) <= limit:
        return {"text": text, "truncated": False, "omittedChars": 0}
    omitted = len(text) - limit
    preview = text[:limit].rstrip()
    preview += f"\n\n... truncated after {limit} chars, omitted {omitted} chars ..."
    return {"text": preview, "truncated": True, "omittedChars": omitted}


@router.get("")
def api_solutions(request: Request, problem_id: str) -> dict:
    """Return expected-result solution files."""
    return route_result(
        lambda: {"solutions": list_solutions(workspace_from_request(request), problem_id)}
    )


@router.post("/upload")
async def api_solutions_upload(
    request: Request,
    problem_id: str,
    files: Annotated[list[UploadFile], File(...)],
) -> dict:
    """Upload one or more expected-result solution files."""
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
    """Create a new expected-result solution source file."""

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
    """Rename an existing expected-result solution source file."""

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


@router.post("/verify/stream")
def api_solutions_verify_stream(
    request: Request, problem_id: str, body: SolutionVerifyRequest
) -> StreamingResponse:
    """Verify expected-result solutions with progress events."""
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
            solutions=body.solutions,
        )
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
    """Queue expected-result solution verification."""
    try:
        ensure_local_write_allowed(request, "solution verification")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
            progress(f"Verifying solutions for {problem_id} on profile {body.profile}.")
            result = verify_solutions(
                workspace,
                problem_id,
                body.profile,
                progress=progress,
                raise_on_failure=False,
                solutions=body.solutions,
            )
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
                "solutions": body.solutions,
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
    """Queue randomized stress testing for expected-result solutions."""
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
    """Return wrong-answer artifacts for a solution verification run."""
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
    """Return stress mismatch artifacts for review."""
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
    """Append a reviewed stress mismatch to cases.yml."""
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
