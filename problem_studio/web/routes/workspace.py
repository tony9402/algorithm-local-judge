from __future__ import annotations

from fastapi import APIRouter, Request

from problem_studio.core.workspace import link_testlib, resolve_workspace, workspace_status
from problem_studio.web.routes.common import route_result, workspace_from_request
from problem_studio.web.schemas import WorkspaceOpenRequest

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("")
def api_workspace(request: Request) -> dict:
    """Return active workspace status."""
    return route_result(lambda: workspace_status(workspace_from_request(request)))


@router.post("/open")
def api_workspace_open(request: Request, body: WorkspaceOpenRequest) -> dict:
    """Switch the active workspace for this local server process."""

    def operation() -> dict:
        request.app.state.workspace = resolve_workspace(body.path)
        return workspace_status(request.app.state.workspace)

    return route_result(operation)


@router.post("/testlib-link")
def api_testlib_link(request: Request) -> dict:
    """Create or refresh problems/testlib.h symlink."""
    return route_result(lambda: link_testlib(workspace_from_request(request)))
