from __future__ import annotations

import json
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import user_data_root
from judge.core.remote_github import github_repository_from_source

DEFAULT_TRUSTED_REPOSITORIES = {"tony9402/algorithm-package"}
TRUST_CONFIG_DIR = "config"
TRUST_CONFIG_FILE = "trusted_repositories.json"


def trusted_repository_config_path() -> Path:
    """Return the user-managed trusted repository allowlist path."""
    return user_data_root() / TRUST_CONFIG_DIR / TRUST_CONFIG_FILE


def normalize_trusted_repository(repository: str) -> str:
    """Normalize a GitHub repository string for trust policy checks."""
    parsed = github_repository_from_source(repository)
    if parsed is None:
        raise JudgeError("trusted repository must look like owner/name or a GitHub URL")
    return parsed.lower()


def default_trusted_repositories() -> list[str]:
    """Return built-in trusted repositories."""
    return sorted(DEFAULT_TRUSTED_REPOSITORIES)


def default_trusted_owner_patterns() -> list[str]:
    """Return built-in trusted repositories for legacy callers."""
    return default_trusted_repositories()


def load_user_trusted_repositories(path: Path | None = None) -> list[str]:
    """Load user-managed trusted repositories."""
    config_path = path or trusted_repository_config_path()
    if not config_path.exists():
        return []
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JudgeError(f"trusted repository config is invalid JSON: {config_path}") from exc
    repositories = data.get("repositories") if isinstance(data, dict) else None
    if not isinstance(repositories, list):
        raise JudgeError(
            f"trusted repository config must contain a repositories list: {config_path}"
        )
    normalized = []
    for item in repositories:
        if not isinstance(item, str):
            raise JudgeError("trusted repository entries must be strings")
        repository = normalize_trusted_repository(item)
        if repository not in normalized:
            normalized.append(repository)
    return sorted(normalized)


def save_user_trusted_repositories(
    repositories: list[str],
    path: Path | None = None,
) -> None:
    """Persist user-managed trusted repositories."""
    config_path = path or trusted_repository_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = sorted({normalize_trusted_repository(repository) for repository in repositories})
    config_path.write_text(
        json.dumps({"repositories": normalized}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def is_default_trusted_repository(repository: str) -> bool:
    """Return whether a repository is trusted by the built-in repository allowlist."""
    normalized = normalize_trusted_repository(repository)
    return normalized in DEFAULT_TRUSTED_REPOSITORIES


def is_trusted_repository(repository: str) -> bool:
    """Return whether a repository is trusted by default or user policy."""
    normalized = normalize_trusted_repository(repository)
    if is_default_trusted_repository(normalized):
        return True
    return normalized in load_user_trusted_repositories()


def ensure_trusted_repository(repository: str) -> str:
    """Return the normalized repository or raise if it is not trusted."""
    normalized = normalize_trusted_repository(repository)
    if not is_trusted_repository(normalized):
        raise JudgeError(
            f"untrusted repository: {normalized}. "
            "Run `judge pack trust add owner/name` before installing from it."
        )
    return normalized


def add_user_trusted_repository(repository: str) -> str:
    """Add a user-managed trusted repository and return the normalized value."""
    normalized = normalize_trusted_repository(repository)
    repositories = load_user_trusted_repositories()
    if normalized not in repositories:
        repositories.append(normalized)
        save_user_trusted_repositories(repositories)
    return normalized


def remove_user_trusted_repository(repository: str) -> str:
    """Remove a user-managed trusted repository and return the normalized value."""
    normalized = normalize_trusted_repository(repository)
    repositories = [item for item in load_user_trusted_repositories() if item != normalized]
    save_user_trusted_repositories(repositories)
    return normalized
