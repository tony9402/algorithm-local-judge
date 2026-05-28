from __future__ import annotations

from fastapi import APIRouter, Request

from problem_studio.core.editor import (
    list_problem_files,
    read_problem_file,
    write_problem_file,
)
from problem_studio.web.routes.common import route_result, workspace_from_request
from problem_studio.web.schemas import FileWriteRequest
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/problems/{problem_id}/files", tags=["files"])


@router.get("")
def api_problem_files(request: Request, problem_id: str) -> dict:
    """Return editable file list for one problem."""
    return route_result(
        lambda: {"files": list_problem_files(workspace_from_request(request), problem_id)}
    )


@router.get("/{file_path:path}")
def api_problem_file_read(request: Request, problem_id: str, file_path: str) -> dict:
    """Read one problem file."""
    return route_result(
        lambda: read_problem_file(workspace_from_request(request), problem_id, file_path)
    )


@router.put("/{file_path:path}")
def api_problem_file_write(
    request: Request, problem_id: str, file_path: str, body: FileWriteRequest
) -> dict:
    """Write one problem file."""

    def operation() -> dict:
        ensure_local_write_allowed(request, "file write")
        return write_problem_file(
            workspace_from_request(request), problem_id, file_path, body.content
        )

    return route_result(operation)
