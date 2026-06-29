"""저장소 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from alj_core.errors import JudgeError
from alj_core.paths import ensure_inside
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
    github_repository = github_repository_from_remote(source)
    if github_repository:
        return github_repository.split("/", 1)[1].removesuffix(".git")
    path = Path(source.strip()).expanduser()
    name = path.name.removesuffix(".git")
    if not name:
        raise JudgeError("repository name could not be inferred from source")
    return name


def validate_repository_name(value: str) -> str:
    """저장소 이름 값이 허용되는 형식과 정책을 만족하는지 검사합니다.

    Args:
        value (str): 검증하거나 상태에 반영할 입력 값입니다.

    Returns:
        str: 정책 검사를 통과한 표준 저장소 이름 문자열입니다.
    """
    name = value.strip().removesuffix(".git")
    if not name or not REPOSITORY_NAME_RE.fullmatch(name):
        raise JudgeError(f"invalid repository name: {value}")
    if name in {".", "..", ".git"} or name.startswith(".") or ".." in name.split("."):
        raise JudgeError(f"invalid repository name: {value}")
    return name


def repository_root(workspace_root: Path, repo_name: str) -> Path:
    name = validate_repository_name(repo_name)
    base = problems_dir(workspace_root)
    return ensure_inside(base / name, base)


def repository_mode_workspace(workspace_root: Path, active_repository: str | None) -> Path:
    if active_repository is None:
        return workspace_root
    root = repository_root(workspace_root, active_repository)
    if not root.exists():
        raise JudgeError(f"problem repository not found: {active_repository}")
    return root


def repository_problem_count(path: Path) -> int:
    try:
        return len(discover_workspace_problem_ids(path))
    except Exception:
        return 0


def repository_summary(workspace_root: Path, repo_name: str) -> dict[str, Any]:
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
    """현재 설정과 파일시스템을 기준으로 저장소 목록을 조회합니다.

    Args:
        workspace_root (Path): 저장소을 계산하거나 검증할 때 필요한 작업 공간 root 입력입니다.

    Returns:
        list[dict[str, Any]]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 저장소 데이터입니다.
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
    workspace_root = resolve_workspace(workspace)
    active = validate_repository_name(active_repository) if active_repository else None
    if active is None:
        return workspace_root, None, workspace_root
    return workspace_root, active, repository_mode_workspace(workspace_root, active)


def repository_context(
    workspace_root: Path,
    active_repository: str | None,
) -> dict[str, Any]:
    repositories = list_repositories(workspace_root)
    return {
        "workspaceRoot": str(workspace_root),
        "activeRepository": active_repository,
        "repositoryMode": active_repository is not None,
        "repositories": repositories,
    }
