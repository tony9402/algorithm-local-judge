from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse

from problem_studio.core.editor import (
    create_solution_file,
    list_problem_files,
    rename_solution_file,
    save_solution_upload,
)
from problem_studio.core.packflow import list_solutions, verify_solutions
from problem_studio.web.routes.common import (
    route_result,
    stream_operation,
    to_http_error,
    workspace_from_request,
)
from problem_studio.web.schemas import (
    SolutionCreateRequest,
    SolutionRenameRequest,
    SolutionVerifyRequest,
)

router = APIRouter(prefix="/api/problems/{problem_id}/solutions", tags=["solutions"])


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
    workspace = workspace_from_request(request)

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
