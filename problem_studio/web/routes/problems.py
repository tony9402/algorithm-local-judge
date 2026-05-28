from __future__ import annotations

from fastapi import APIRouter, Request

from judge.core.problem import load_problem
from problem_studio.core.editor import list_problem_files, update_problem_metadata
from problem_studio.core.templates import create_problem
from problem_studio.core.workspace import (
    delete_problem,
    list_problem_metadata,
    rename_problem,
)
from problem_studio.web.routes.common import (
    add_workspace_warning,
    route_result,
    workspace_from_request,
    workspace_status_from_request,
)
from problem_studio.web.schemas import (
    MetadataPatchRequest,
    ProblemCreateRequest,
    ProblemDeleteRequest,
    ProblemRenameRequest,
)
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/problems", tags=["problems"])


@router.get("")
def api_problems(request: Request) -> list[dict]:
    """Return problem summaries."""
    return route_result(lambda: list_problem_metadata(workspace_from_request(request)))


@router.post("")
def api_problem_create(request: Request, body: ProblemCreateRequest) -> dict:
    """Create a new problem from templates."""

    def operation() -> dict:
        ensure_local_write_allowed(request, "problem creation")
        workspace = workspace_from_request(request)
        result = create_problem(
            workspace,
            body.problem_id,
            body.title,
            body.folder,
            body.version,
            body.default_profile,
            body.limits,
        )
        result["workspace"] = workspace_status_from_request(request)
        return result

    return route_result(operation)


@router.get("/{problem_id}")
def api_problem_detail(request: Request, problem_id: str) -> dict:
    """Return metadata and editable files for one problem."""

    def operation() -> dict:
        workspace = workspace_from_request(request)
        problem_dir, metadata_path, metadata = load_problem(problem_id, workspace)
        return {
            "problemId": problem_id,
            "path": str(problem_dir),
            "metadataPath": str(metadata_path),
            "metadata": metadata,
            "files": list_problem_files(workspace, problem_id),
        }

    return route_result(operation)


@router.patch("/{problem_id}/metadata")
def api_problem_metadata_patch(
    request: Request, problem_id: str, body: MetadataPatchRequest
) -> dict:
    """Patch problem.json metadata."""
    return route_result(
        lambda: (
            ensure_local_write_allowed(request, "problem metadata update")
            or update_problem_metadata(workspace_from_request(request), problem_id, body.metadata)
        )
    )


@router.patch("/{problem_id}/id")
def api_problem_rename(request: Request, problem_id: str, body: ProblemRenameRequest) -> dict:
    """Change a problem id and rename its directory."""

    def operation() -> dict:
        ensure_local_write_allowed(request, "problem rename")
        result = rename_problem(workspace_from_request(request), problem_id, body.problem_id)
        result["workspace"] = add_workspace_warning(request, result["workspace"])
        return result

    return route_result(operation)


@router.delete("/{problem_id}")
def api_problem_delete(request: Request, problem_id: str, body: ProblemDeleteRequest) -> dict:
    """Delete a problem after exact confirmation."""

    def operation() -> dict:
        ensure_local_write_allowed(request, "problem delete")
        result = delete_problem(
            workspace_from_request(request),
            problem_id,
            body.confirm_phrase,
        )
        result["workspace"] = add_workspace_warning(request, result["workspace"])
        return result

    return route_result(operation)
