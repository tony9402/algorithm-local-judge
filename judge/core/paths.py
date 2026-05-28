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
    """Return the repository root inferred from the installed package path."""
    if configured := os.environ.get(ENV_PROJECT_ROOT):
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    """Return whether the process is running from a frozen standalone binary."""
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Return the root directory that owns the running application."""
    if is_frozen():
        executable = Path(sys.executable).resolve()
        if executable.parent.name == "bin":
            return executable.parent.parent
        return executable.parent
    return repo_root()


def _configured_path(env_name: str) -> Path | None:
    """Return an expanded path from an environment variable if it is set."""
    value = os.environ.get(env_name)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _windows_local_app_data() -> Path:
    """Return the base local app data directory on Windows-like environments."""
    value = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if value:
        return Path(value).expanduser()
    return Path.home() / "AppData" / "Local"


def user_data_root() -> Path:
    """Return the per-user directory for installed packs and configuration."""
    if configured := _configured_path(ENV_DATA_HOME):
        return configured
    if os.name == "nt":
        return (_windows_local_app_data() / APP_NAME).resolve()
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (base / APP_NAME).expanduser().resolve()


def default_cache_root() -> Path:
    """Return the per-user cache directory for generated data and run artifacts."""
    if configured := _configured_path(ENV_CACHE_HOME):
        return configured
    if os.name == "nt":
        return (_windows_local_app_data() / APP_NAME / "cache").resolve()
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return (base / APP_NAME).expanduser().resolve()


def problem_pack_root() -> Path:
    """Return the directory where standalone problem packs are installed."""
    if configured := _configured_path(ENV_PACK_HOME):
        return configured
    return user_data_root() / "problem-packs"


def problem_source_root() -> Path:
    """Return the directory where source problem packages are installed."""
    if configured := _configured_path(ENV_SOURCE_HOME):
        return configured
    return user_data_root() / "problem-sources"


def cache_root(root: Path | None = None) -> Path:
    """Return the root directory for generated data and run artifacts."""
    if root is not None:
        return root / ".judge-cache"
    return default_cache_root()


def build_root(root: Path | None = None) -> Path:
    """Return the root directory for compiled helper binaries."""
    return (root or repo_root()) / "build"


def rel(path: Path, root: Path | None = None) -> str:
    """Format a path relative to a useful runtime root when possible."""
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
    """Return the executable suffix for the current operating system."""
    return ".exe" if os.name == "nt" else ""


def normalized_arch(machine: str | None = None) -> str:
    """Normalize platform machine names into release architecture ids."""
    value = (machine or platform.machine()).lower()
    if value in {"x86_64", "amd64"}:
        return "amd64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    return value or "unknown"


def normalized_os(system: str | None = None) -> str:
    """Normalize operating system names into release os ids."""
    value = (system or platform.system()).lower()
    if value == "darwin":
        return "macos"
    if value == "windows":
        return "windows"
    if value == "linux":
        return "linux"
    return value or "unknown"


def current_platform_id() -> str:
    """Return the release platform id for this runtime."""
    return f"{normalized_os()}-{normalized_arch()}"


def ensure_inside(path: Path, base: Path) -> Path:
    """Return a resolved path only if it stays inside the given base."""
    path = path.resolve()
    base = base.resolve()
    if path == base or base in path.parents:
        return path
    raise JudgeError(f"refusing to access path outside cache: {path}")


def validate_safe_id(name: str, value: str) -> None:
    """Validate a CLI-visible id before using it in filesystem paths."""
    if not value or not SAFE_ID_RE.fullmatch(value):
        raise JudgeError(f"invalid {name}: {value}")
