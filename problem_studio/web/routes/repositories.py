from __future__ import annotations

from fastapi import APIRouter, Request

from judge.core.errors import JudgeError
from problem_studio.core.git import git_status
from problem_studio.core.repositories import (
    clone_problem_repository,
    list_repositories,
    repository_summary,
)
from problem_studio.web.routes.common import (
    active_repository_from_request,
    route_result,
    set_active_repository,
    workspace_root_from_request,
    workspace_status_from_request,
)
from problem_studio.web.schemas import (
    RepositoryCloneRequest,
    RepositoryRegisterRequest,
    RepositorySelectRequest,
)
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


def ensure_repository_write_enabled(request: Request) -> None:
    """Block repository mutations when local Git write actions are disabled."""
    ensure_local_write_allowed(request, "repository Git action")
    if not getattr(request.app.state, "git_write_enabled", True):
        raise JudgeError("Git network/write actions are disabled for this server binding")


def repository_response(request: Request) -> dict:
    """Return repository selection state for the UI."""
    workspace_root = workspace_root_from_request(request)
    return {
        "workspaceRoot": str(workspace_root),
        "activeRepository": active_repository_from_request(request),
        "repositoryMode": active_repository_from_request(request) is not None,
        "repositories": list_repositories(workspace_root),
    }


def selected_payload(request: Request) -> dict:
    """Return the full payload after a repository selection change."""
    workspace = workspace_status_from_request(request)
    git = git_status(request.app.state.workspace)
    git["writeEnabled"] = bool(getattr(request.app.state, "git_write_enabled", True))
    git["workspaceRoot"] = workspace["workspaceRoot"]
    git["repositoryName"] = workspace["activeRepository"]
    git["repositoryPath"] = workspace["workspace"]
    git["repositoryMode"] = workspace["repositoryMode"]
    return {
        "workspace": workspace,
        "repositories": repository_response(request),
        "git": git,
    }


@router.get("")
def api_repositories(request: Request) -> dict:
    """Return nested problem repositories available in this workspace."""
    return route_result(lambda: repository_response(request))


@router.post("/select")
def api_repository_select(request: Request, body: RepositorySelectRequest) -> dict:
    """Switch the active nested problem repository."""

    def operation() -> dict:
        set_active_repository(request, body.repo_name)
        return selected_payload(request)

    return route_result(operation)


@router.post("/clone")
def api_repository_clone(request: Request, body: RepositoryCloneRequest) -> dict:
    """Clone a problem repository under workspace/problems/{repo_name} and select it."""

    def operation() -> dict:
        ensure_repository_write_enabled(request)
        summary = clone_problem_repository(
            workspace_root_from_request(request),
            body.url,
            body.branch,
            body.repo_name,
        )
        set_active_repository(request, summary["name"])
        payload = selected_payload(request)
        payload["repository"] = summary
        return payload

    return route_result(operation)


@router.post("/register")
def api_repository_register(request: Request, body: RepositoryRegisterRequest) -> dict:
    """Open an existing nested problem repository."""

    def operation() -> dict:
        set_active_repository(request, body.repo_name)
        payload = selected_payload(request)
        payload["repository"] = repository_summary(
            workspace_root_from_request(request),
            body.repo_name,
        )
        return payload

    return route_result(operation)
