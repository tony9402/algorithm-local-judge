"""경로 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from alj_core.config import SAFE_ID_RE
from alj_core.errors import JudgeError

APP_NAME = "algorithm-local-judge"
ENV_PROJECT_ROOT = "ALJ_PROJECT_ROOT"
ENV_DATA_HOME = "ALJ_DATA_HOME"
ENV_CACHE_HOME = "ALJ_CACHE_HOME"
ENV_PACK_HOME = "ALJ_PACK_HOME"
ENV_SOURCE_HOME = "ALJ_SOURCE_HOME"


def repo_root() -> Path:
    if configured := os.environ.get(ENV_PROJECT_ROOT):
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def is_frozen() -> bool:
    """frozen 여부를 실제 파일, 설정, 또는 런타임 상태를 기준으로 판정합니다.

    Returns:
        bool: frozen 조건을 만족하면 True, 아니면 False입니다.
    """
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    if is_frozen():
        executable = Path(sys.executable).resolve()
        if executable.parent.name == "bin":
            return executable.parent.parent
        return executable.parent
    return repo_root()


def _configured_path(env_name: str) -> Path | None:
    value = os.environ.get(env_name)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _windows_local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if value:
        return Path(value).expanduser()
    return Path.home() / "AppData" / "Local"


def user_data_root() -> Path:
    if configured := _configured_path(ENV_DATA_HOME):
        return configured
    if os.name == "nt":
        return (_windows_local_app_data() / APP_NAME).resolve()
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (base / APP_NAME).expanduser().resolve()


def default_cache_root() -> Path:
    if configured := _configured_path(ENV_CACHE_HOME):
        return configured
    if os.name == "nt":
        return (_windows_local_app_data() / APP_NAME / "cache").resolve()
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return (base / APP_NAME).expanduser().resolve()


def problem_pack_root() -> Path:
    if configured := _configured_path(ENV_PACK_HOME):
        return configured
    return user_data_root() / "problem-packs"


def problem_source_root() -> Path:
    if configured := _configured_path(ENV_SOURCE_HOME):
        return configured
    return user_data_root() / "problem-sources"


def cache_root(root: Path | None = None) -> Path:
    if root is not None:
        return root / ".judge-cache"
    return default_cache_root()


def build_root(root: Path | None = None) -> Path:
    """root에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Args:
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.

    Returns:
        Path: 검증된 root 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    return (root or repo_root()) / "build"


def rel(path: Path, root: Path | None = None) -> str:
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
    return ".exe" if os.name == "nt" else ""


def normalized_arch(machine: str | None = None) -> str:
    value = (machine or platform.machine()).lower()
    if value in {"x86_64", "amd64"}:
        return "amd64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    return value or "unknown"


def normalized_os(system: str | None = None) -> str:
    value = (system or platform.system()).lower()
    if value == "darwin":
        return "macos"
    if value == "windows":
        return "windows"
    if value == "linux":
        return "linux"
    return value or "unknown"


def current_platform_id() -> str:
    return f"{normalized_os()}-{normalized_arch()}"


def ensure_inside(path: Path, base: Path) -> Path:
    """inside 조건을 확인하고 위반 시 호출자가 중단할 수 있는 예외를 발생시킵니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
        base (Path): inside을 계산하거나 검증할 때 필요한 base 입력입니다.

    Returns:
        Path: 검증된 inside 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    path = path.resolve()
    base = base.resolve()
    if path == base or base in path.parents:
        return path
    raise JudgeError(f"refusing to access path outside cache: {path}")


def validate_safe_id(name: str, value: str) -> None:
    """안전 ID 값이 허용되는 형식과 정책을 만족하는지 검사합니다.

    Args:
        name (str): 사용자 표시와 내부 조회에 함께 쓰는 항목 이름입니다.
        value (str): 검증하거나 상태에 반영할 입력 값입니다.
    """
    if not value or not SAFE_ID_RE.fullmatch(value):
        raise JudgeError(f"invalid {name}: {value}")
