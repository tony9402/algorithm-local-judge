"""remote_trust 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
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
    """trusted_repository_config_path 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    return user_data_root() / TRUST_CONFIG_DIR / TRUST_CONFIG_FILE


def normalize_trusted_repository(repository: str) -> str:
    """normalize_trusted_repository 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repository (str): `repository` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    parsed = github_repository_from_source(repository)
    if parsed is None:
        raise JudgeError("trusted repository must look like owner/name or a GitHub URL")
    return parsed.lower()


def default_trusted_repositories() -> list[str]:
    """default_trusted_repositories 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        list[str]: 처리 결과를 반환합니다.
    """
    return sorted(DEFAULT_TRUSTED_REPOSITORIES)


def default_trusted_owner_patterns() -> list[str]:
    """default_trusted_owner_patterns 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        list[str]: 처리 결과를 반환합니다.
    """
    return default_trusted_repositories()


def load_user_trusted_repositories(path: Path | None = None) -> list[str]:
    """load_user_trusted_repositories 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path | None): 경로 문자열입니다.
    
    Returns:
        list[str]: 처리 결과를 반환합니다.
    """
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
    """save_user_trusted_repositories 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repositories (list[str]): `repositories` 값입니다.
        path (Path | None): 경로 문자열입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    config_path = path or trusted_repository_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = sorted({normalize_trusted_repository(repository) for repository in repositories})
    config_path.write_text(
        json.dumps({"repositories": normalized}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def is_default_trusted_repository(repository: str) -> bool:
    """is_default_trusted_repository 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repository (str): `repository` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    normalized = normalize_trusted_repository(repository)
    return normalized in DEFAULT_TRUSTED_REPOSITORIES


def is_trusted_repository(repository: str) -> bool:
    """is_trusted_repository 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repository (str): `repository` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    normalized = normalize_trusted_repository(repository)
    if is_default_trusted_repository(normalized):
        return True
    return normalized in load_user_trusted_repositories()


def ensure_trusted_repository(repository: str) -> str:
    """ensure_trusted_repository 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repository (str): `repository` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    normalized = normalize_trusted_repository(repository)
    if not is_trusted_repository(normalized):
        raise JudgeError(
            f"untrusted repository: {normalized}. "
            "Run `judge pack trust add owner/name` before installing from it."
        )
    return normalized


def add_user_trusted_repository(repository: str) -> str:
    """add_user_trusted_repository 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repository (str): `repository` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    normalized = normalize_trusted_repository(repository)
    repositories = load_user_trusted_repositories()
    if normalized not in repositories:
        repositories.append(normalized)
        save_user_trusted_repositories(repositories)
    return normalized


def remove_user_trusted_repository(repository: str) -> str:
    """remove_user_trusted_repository 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repository (str): `repository` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    normalized = normalize_trusted_repository(repository)
    repositories = [item for item in load_user_trusted_repositories() if item != normalized]
    save_user_trusted_repositories(repositories)
    return normalized
