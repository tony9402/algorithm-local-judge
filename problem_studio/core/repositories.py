"""repositories 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.paths import ensure_inside
from problem_studio.core.git import (
    clone_repository,
    current_branch,
    github_repository_from_remote,
    is_git_repository,
    remote_url,
)
from problem_studio.core.workspace import (
    discover_workspace_problem_ids,
    problems_dir,
    resolve_workspace,
)

REPOSITORY_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def repository_name_from_source(source: str) -> str:
    """repository_name_from_source 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (str): `source` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    github_repository = github_repository_from_remote(source)
    if github_repository:
        return github_repository.split("/", 1)[1].removesuffix(".git")
    path = Path(source.strip()).expanduser()
    name = path.name.removesuffix(".git")
    if not name:
        raise JudgeError("repository name could not be inferred from source")
    return name


def validate_repository_name(value: str) -> str:
    """validate_repository_name 함수를 실행하고 결과를 반환합니다.
    
    Args:
        value (str): 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    name = value.strip().removesuffix(".git")
    if not name or not REPOSITORY_NAME_RE.fullmatch(name):
        raise JudgeError(f"invalid repository name: {value}")
    if name in {".", "..", ".git"} or name.startswith(".") or ".." in name.split("."):
        raise JudgeError(f"invalid repository name: {value}")
    return name


def repository_root(workspace_root: Path, repo_name: str) -> Path:
    """repository_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace_root (Path): `workspace_root` 값입니다.
        repo_name (str): `repo_name` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    name = validate_repository_name(repo_name)
    base = problems_dir(workspace_root)
    return ensure_inside(base / name, base)


def repository_mode_workspace(workspace_root: Path, active_repository: str | None) -> Path:
    """repository_mode_workspace 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace_root (Path): `workspace_root` 값입니다.
        active_repository (str | None): `active_repository` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if active_repository is None:
        return workspace_root
    root = repository_root(workspace_root, active_repository)
    if not root.exists():
        raise JudgeError(f"problem repository not found: {active_repository}")
    return root


def repository_problem_count(path: Path) -> int:
    """repository_problem_count 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
    try:
        return len(discover_workspace_problem_ids(path))
    except Exception:
        return 0


def repository_summary(workspace_root: Path, repo_name: str) -> dict[str, Any]:
    """repository_summary 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace_root (Path): `workspace_root` 값입니다.
        repo_name (str): `repo_name` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    root = repository_root(workspace_root, repo_name)
    branch = None
    remote = None
    is_repository = is_git_repository(root)
    if is_repository:
        try:
            branch = current_branch(root)
        except Exception:
            branch = None
        try:
            remote = remote_url(root)
        except Exception:
            remote = None
    return {
        "name": repo_name,
        "path": str(root),
        "label": repo_name,
        "isRepository": is_repository,
        "branch": branch,
        "remote": remote,
        "problemCount": repository_problem_count(root),
    }


def list_repositories(workspace_root: Path) -> list[dict[str, Any]]:
    """list_repositories 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace_root (Path): `workspace_root` 값입니다.
    
    Returns:
        list[dict[str, Any]]: 처리 결과를 반환합니다.
    """
    base = problems_dir(workspace_root)
    if not base.exists():
        return []
    repositories = []
    for child in sorted(path for path in base.iterdir() if path.is_dir()):
        if (child / ".git").exists():
            repositories.append(repository_summary(workspace_root, child.name))
    return repositories


def same_repository_source(existing_remote: str | None, requested_source: str) -> bool:
    """same_repository_source 함수를 실행하고 결과를 반환합니다.
    
    Args:
        existing_remote (str | None): `existing_remote` 값입니다.
        requested_source (str): `requested_source` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    if not existing_remote:
        return False
    existing_github = github_repository_from_remote(existing_remote)
    requested_github = github_repository_from_remote(requested_source)
    if existing_github and requested_github:
        return existing_github == requested_github
    try:
        existing_path = Path(existing_remote).expanduser().resolve()
        requested_path = Path(requested_source).expanduser().resolve()
        return existing_path == requested_path
    except Exception:
        return existing_remote.rstrip("/") == requested_source.strip().rstrip("/")


def clone_problem_repository(
    workspace_root: Path,
    source: str,
    branch: str | None = None,
    repo_name: str | None = None,
) -> dict[str, Any]:
    """clone_problem_repository 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace_root (Path): `workspace_root` 값입니다.
        source (str): `source` 값입니다.
        branch (str | None): `branch` 값입니다.
        repo_name (str | None): `repo_name` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    workspace_root = resolve_workspace(workspace_root)
    name = validate_repository_name(repo_name or repository_name_from_source(source))
    target = repository_root(workspace_root, name)

    if target.exists() and any(target.iterdir()):
        if (target / ".git").exists():
            existing_remote = remote_url(target)
            if same_repository_source(existing_remote, source):
                return repository_summary(workspace_root, name)
            raise JudgeError(
                f"repository target already exists with a different remote: {target}"
            )
        if (target / "problem.json").exists():
            raise JudgeError(f"clone target is an existing problem directory: {target}")
        raise JudgeError(f"clone target is not empty: {target}")

    clone_repository(source, target, branch)
    return repository_summary(workspace_root, name)


def initialize_problem_repository_workspace(
    workspace: Path | str | None,
    active_repository: str | None = None,
) -> tuple[Path, str | None, Path]:
    """initialize_problem_repository_workspace 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path | str | None): 작업 공간 객체입니다.
        active_repository (str | None): `active_repository` 값입니다.
    
    Returns:
        tuple[Path, str | None, Path]: 처리 결과를 반환합니다.
    """
    workspace_root = resolve_workspace(workspace)
    active = validate_repository_name(active_repository) if active_repository else None
    if active is None:
        return workspace_root, None, workspace_root
    return workspace_root, active, repository_mode_workspace(workspace_root, active)


def repository_context(
    workspace_root: Path,
    active_repository: str | None,
) -> dict[str, Any]:
    """repository_context 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace_root (Path): `workspace_root` 값입니다.
        active_repository (str | None): `active_repository` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    repositories = list_repositories(workspace_root)
    return {
        "workspaceRoot": str(workspace_root),
        "activeRepository": active_repository,
        "repositoryMode": active_repository is not None,
        "repositories": repositories,
    }
