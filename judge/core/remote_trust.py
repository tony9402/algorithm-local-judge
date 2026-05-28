"""원격 신뢰 설정 도메인 로직과 파일시스템 변경 정책을 담당합니다.
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
    return user_data_root() / TRUST_CONFIG_DIR / TRUST_CONFIG_FILE


def normalize_trusted_repository(repository: str) -> str:
    """trusted 저장소 입력을 비교와 저장에 쓰기 쉬운 표준 형식으로 정규화합니다.

    Args:
        repository (str): GitHub owner/name 또는 URL에서 정규화할 저장소 식별자입니다.

    Returns:
        str: 정책 검사를 통과한 표준 trusted 저장소 문자열입니다.
    """
    parsed = github_repository_from_source(repository)
    if parsed is None:
        raise JudgeError("trusted repository must look like owner/name or a GitHub URL")
    return parsed.lower()


def default_trusted_repositories() -> list[str]:
    return sorted(DEFAULT_TRUSTED_REPOSITORIES)


def default_trusted_owner_patterns() -> list[str]:
    return default_trusted_repositories()


def load_user_trusted_repositories(path: Path | None = None) -> list[str]:
    """user trusted 저장소 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        path (Path | None): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.

    Returns:
        list[str]: 호출자가 순회하거나 화면에 표시할 user trusted 저장소 항목 목록입니다.
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
    """user trusted 저장소 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        repositories (list[str]): user trusted 저장소을 계산하거나 검증할 때 필요한 저장소 입력입니다.
        path (Path | None): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
    """
    config_path = path or trusted_repository_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = sorted({normalize_trusted_repository(repository) for repository in repositories})
    config_path.write_text(
        json.dumps({"repositories": normalized}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def is_default_trusted_repository(repository: str) -> bool:
    """default trusted 저장소 여부를 실제 파일, 설정, 또는 런타임 상태를 기준으로 판정합니다.

    Args:
        repository (str): GitHub owner/name 또는 URL에서 정규화할 저장소 식별자입니다.

    Returns:
        bool: default trusted 저장소 조건을 만족하면 True, 아니면 False입니다.
    """
    normalized = normalize_trusted_repository(repository)
    return normalized in DEFAULT_TRUSTED_REPOSITORIES


def is_trusted_repository(repository: str) -> bool:
    """trusted 저장소 여부를 실제 파일, 설정, 또는 런타임 상태를 기준으로 판정합니다.

    Args:
        repository (str): GitHub owner/name 또는 URL에서 정규화할 저장소 식별자입니다.

    Returns:
        bool: trusted 저장소 조건을 만족하면 True, 아니면 False입니다.
    """
    normalized = normalize_trusted_repository(repository)
    if is_default_trusted_repository(normalized):
        return True
    return normalized in load_user_trusted_repositories()


def ensure_trusted_repository(repository: str) -> str:
    """trusted 저장소 조건을 확인하고 위반 시 호출자가 중단할 수 있는 예외를 발생시킵니다.

    Args:
        repository (str): GitHub owner/name 또는 URL에서 정규화할 저장소 식별자입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 trusted 저장소 문자열입니다.
    """
    normalized = normalize_trusted_repository(repository)
    if not is_trusted_repository(normalized):
        raise JudgeError(
            f"untrusted repository: {normalized}. "
            "Run `judge pack trust add owner/name` before installing from it."
        )
    return normalized


def add_user_trusted_repository(repository: str) -> str:
    normalized = normalize_trusted_repository(repository)
    repositories = load_user_trusted_repositories()
    if normalized not in repositories:
        repositories.append(normalized)
        save_user_trusted_repositories(repositories)
    return normalized


def remove_user_trusted_repository(repository: str) -> str:
    """user trusted 저장소 항목을 현재 상태와 저장소에서 제거합니다.

    Args:
        repository (str): GitHub owner/name 또는 URL에서 정규화할 저장소 식별자입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 user trusted 저장소 문자열입니다.
    """
    normalized = normalize_trusted_repository(repository)
    repositories = [item for item in load_user_trusted_repositories() if item != normalized]
    save_user_trusted_repositories(repositories)
    return normalized
