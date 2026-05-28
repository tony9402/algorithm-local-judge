"""paths 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from judge.core.config import SAFE_ID_RE
from judge.core.errors import JudgeError

APP_NAME = "algorithm-local-judge"
ENV_PROJECT_ROOT = "ALJ_PROJECT_ROOT"
ENV_DATA_HOME = "ALJ_DATA_HOME"
ENV_CACHE_HOME = "ALJ_CACHE_HOME"
ENV_PACK_HOME = "ALJ_PACK_HOME"
ENV_SOURCE_HOME = "ALJ_SOURCE_HOME"


def repo_root() -> Path:
    """repo_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if configured := os.environ.get(ENV_PROJECT_ROOT):
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    """is_frozen 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """app_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if is_frozen():
        executable = Path(sys.executable).resolve()
        if executable.parent.name == "bin":
            return executable.parent.parent
        return executable.parent
    return repo_root()


def _configured_path(env_name: str) -> Path | None:
    """_configured_path 함수를 실행하고 결과를 반환합니다.
    
    Args:
        env_name (str): `env_name` 값입니다.
    
    Returns:
        Path | None: 처리 결과를 반환합니다.
    """
    value = os.environ.get(env_name)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _windows_local_app_data() -> Path:
    """_windows_local_app_data 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    value = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if value:
        return Path(value).expanduser()
    return Path.home() / "AppData" / "Local"


def user_data_root() -> Path:
    """user_data_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if configured := _configured_path(ENV_DATA_HOME):
        return configured
    if os.name == "nt":
        return (_windows_local_app_data() / APP_NAME).resolve()
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (base / APP_NAME).expanduser().resolve()


def default_cache_root() -> Path:
    """default_cache_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if configured := _configured_path(ENV_CACHE_HOME):
        return configured
    if os.name == "nt":
        return (_windows_local_app_data() / APP_NAME / "cache").resolve()
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return (base / APP_NAME).expanduser().resolve()


def problem_pack_root() -> Path:
    """problem_pack_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if configured := _configured_path(ENV_PACK_HOME):
        return configured
    return user_data_root() / "problem-packs"


def problem_source_root() -> Path:
    """problem_source_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if configured := _configured_path(ENV_SOURCE_HOME):
        return configured
    return user_data_root() / "problem-sources"


def cache_root(root: Path | None = None) -> Path:
    """cache_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        root (Path | None): `root` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if root is not None:
        return root / ".judge-cache"
    return default_cache_root()


def build_root(root: Path | None = None) -> Path:
    """build_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        root (Path | None): `root` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    return (root or repo_root()) / "build"


def rel(path: Path, root: Path | None = None) -> str:
    """rel 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    roots = (
        [root] if root is not None else [repo_root(), app_root(), user_data_root(), cache_root()]
    )
    resolved = path.resolve()
    for candidate in roots:
        if candidate is None:
            continue
        try:
            return str(resolved.relative_to(candidate.resolve()))
        except ValueError:
            continue
    return str(path)


def executable_suffix() -> str:
    """executable_suffix 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    return ".exe" if os.name == "nt" else ""


def normalized_arch(machine: str | None = None) -> str:
    """normalized_arch 함수를 실행하고 결과를 반환합니다.
    
    Args:
        machine (str | None): `machine` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    value = (machine or platform.machine()).lower()
    if value in {"x86_64", "amd64"}:
        return "amd64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    return value or "unknown"


def normalized_os(system: str | None = None) -> str:
    """normalized_os 함수를 실행하고 결과를 반환합니다.
    
    Args:
        system (str | None): `system` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    value = (system or platform.system()).lower()
    if value == "darwin":
        return "macos"
    if value == "windows":
        return "windows"
    if value == "linux":
        return "linux"
    return value or "unknown"


def current_platform_id() -> str:
    """current_platform_id 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    return f"{normalized_os()}-{normalized_arch()}"


def ensure_inside(path: Path, base: Path) -> Path:
    """ensure_inside 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
        base (Path): `base` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    path = path.resolve()
    base = base.resolve()
    if path == base or base in path.parents:
        return path
    raise JudgeError(f"refusing to access path outside cache: {path}")


def validate_safe_id(name: str, value: str) -> None:
    """validate_safe_id 함수를 실행하고 결과를 반환합니다.
    
    Args:
        name (str): 이름입니다.
        value (str): 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    if not value or not SAFE_ID_RE.fullmatch(value):
        raise JudgeError(f"invalid {name}: {value}")
