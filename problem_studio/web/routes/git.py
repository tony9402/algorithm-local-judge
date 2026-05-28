from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from judge.core.errors import JudgeError
from problem_studio.core.git import (
    clone_repository,
    commit_changes,
    fetch_repository,
    git_status,
    pull_repository,
    push_repository,
)
from problem_studio.core.workspace import workspace_status
from problem_studio.web.routes.common import (
    active_repository_from_request,
    add_workspace_warning,
    route_result,
    workspace_from_request,
    workspace_root_from_request,
)
from problem_studio.web.schemas import GitCloneRequest, GitCommitRequest
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/workspace/git", tags=["workspace-git"])


def ensure_git_write_enabled(request: Request) -> None:
    """Block Git mutations when the server was not started for local-only use."""
    ensure_local_write_allowed(request, "Git network/write action")
    if not getattr(request.app.state, "git_write_enabled", True):
        raise JudgeError("Git network/write actions are disabled for this server binding")


def attach_git_write_policy(request: Request, status: dict) -> dict:
    """Attach the server-side Git write policy to a Git status payload."""
    status["writeEnabled"] = bool(getattr(request.app.state, "git_write_enabled", True))
    status["workspaceRoot"] = str(workspace_root_from_request(request))
    status["repositoryName"] = active_repository_from_request(request)
    status["repositoryPath"] = str(workspace_from_request(request))
    status["repositoryMode"] = active_repository_from_request(request) is not None
    return status


def status_payload(request: Request) -> dict:
    """Return Git status with the server-side write policy."""
    return attach_git_write_policy(request, git_status(workspace_from_request(request)))


@router.get("/status")
def api_git_status(request: Request) -> dict:
    """Return Git status for the current workspace."""
    return route_result(lambda: status_payload(request))


@router.post("/clone")
def api_git_clone(request: Request, body: GitCloneRequest) -> dict:
    """Clone a Git repository and switch the active workspace."""

    def operation() -> dict:
        ensure_git_write_enabled(request)
        target = Path(body.path)
        clone_repository(body.url, target, body.branch)
        request.app.state.workspace_root = target.expanduser().resolve()
        request.app.state.active_repository = None
        request.app.state.workspace = request.app.state.workspace_root
        return {
            "workspace": add_workspace_warning(
                request,
                workspace_status(request.app.state.workspace),
            ),
            "git": status_payload(request),
        }

    return route_result(operation)


@router.post("/fetch")
def api_git_fetch(request: Request) -> dict:
    """Fetch remote changes."""

    def operation() -> dict:
        ensure_git_write_enabled(request)
        return attach_git_write_policy(request, fetch_repository(workspace_from_request(request)))

    return route_result(operation)


@router.post("/pull")
def api_git_pull(request: Request) -> dict:
    """Fast-forward pull the current branch."""

    def operation() -> dict:
        ensure_git_write_enabled(request)
        return attach_git_write_policy(request, pull_repository(workspace_from_request(request)))

    return route_result(operation)


@router.post("/commit")
def api_git_commit(request: Request, body: GitCommitRequest) -> dict:
    """Commit allowed problem workspace files."""

    def operation() -> dict:
        ensure_git_write_enabled(request)
        return attach_git_write_policy(
            request,
            commit_changes(workspace_from_request(request), body.message, body.files),
        )

    return route_result(operation)


@router.post("/push")
def api_git_push(request: Request) -> dict:
    """Push the current branch."""

    def operation() -> dict:
        ensure_git_write_enabled(request)
        return attach_git_write_policy(request, push_repository(workspace_from_request(request)))

    return route_result(operation)
