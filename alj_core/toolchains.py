"""Managed toolchain installation, activation, and executable resolution."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from alj_core.errors import JudgeError
from alj_core.pack_archive import safe_extract_tar
from alj_core.paths import current_platform_id, user_data_root
from alj_core.toolchain_manifest import ToolchainManifest, load_toolchain_manifest

ENV_TOOLCHAIN_HOME = "ALJ_TOOLCHAIN_HOME"
ACTIVE_POINTER_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ToolResolutionSpec:
    env_name: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedTool:
    tool_id: str
    path: str
    source: str
    env_name: str
    profile_id: str | None = None
    profile_version: str | None = None


@dataclass(frozen=True)
class ToolchainInstallResult:
    profile_id: str
    version: str
    path: Path
    reused: bool
    downloaded: bool


TOOL_SPECS = {
    "cxx": ToolResolutionSpec("ALJ_CXX", ("g++",)),
    "javac": ToolResolutionSpec("ALJ_JAVAC", ("javac",)),
    "java": ToolResolutionSpec("ALJ_JAVA", ("java",)),
    "python": ToolResolutionSpec("ALJ_PYTHON", ("python3", "python")),
    "pypy": ToolResolutionSpec("ALJ_PYPY", ("pypy3", "pypy")),
}


def toolchain_root(root: Path | None = None) -> Path:
    if root is not None:
        return root.resolve()
    if configured := os.environ.get(ENV_TOOLCHAIN_HOME):
        return Path(configured).expanduser().resolve()
    return user_data_root() / "toolchains"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _profile_path(manifest: ToolchainManifest, root: Path) -> Path:
    return root / "profiles" / manifest.profile_id / manifest.version


def _active_pointer_path(root: Path) -> Path:
    return root / "active.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _write_active_pointer(manifest: ToolchainManifest, root: Path) -> None:
    _atomic_write_json(
        _active_pointer_path(root),
        {
            "schemaVersion": ACTIVE_POINTER_SCHEMA_VERSION,
            "profileId": manifest.profile_id,
            "version": manifest.version,
            "platformId": manifest.platform_id,
        },
    )


def _read_active_pointer(root: Path) -> dict[str, Any] | None:
    path = _active_pointer_path(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise JudgeError(f"managed toolchain active pointer is invalid: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schemaVersion") != ACTIVE_POINTER_SCHEMA_VERSION
    ):
        raise JudgeError("managed toolchain active pointer has an unsupported schema")
    for key in ("profileId", "version", "platformId"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise JudgeError(f"managed toolchain active pointer is missing {key}")
    return payload


def _validate_tool(path: Path, expected_sha256: str, label: str) -> None:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise JudgeError(f"managed toolchain executable is missing or not executable: {label}")
    if _sha256_file(path) != expected_sha256:
        raise JudgeError(f"managed toolchain executable hash mismatch: {label}")


def _validate_profile(path: Path, manifest: ToolchainManifest) -> None:
    if manifest.platform_id != current_platform_id():
        raise JudgeError(
            f"toolchain platform mismatch: {manifest.platform_id} != {current_platform_id()}"
        )
    resolved_root = path.resolve()
    for tool_id, tool in manifest.tools.items():
        executable = (path / PurePosixPath(tool.path)).resolve()
        if executable != resolved_root and resolved_root not in executable.parents:
            raise JudgeError(f"managed toolchain path escapes profile: {tool_id}")
        _validate_tool(executable, tool.sha256, tool_id)


def _installed_manifest(path: Path) -> ToolchainManifest:
    return load_toolchain_manifest(path / "manifest.json")


def _matching_installed_profile(path: Path, expected: ToolchainManifest) -> bool:
    try:
        installed = _installed_manifest(path)
        if installed.to_dict() != expected.to_dict():
            return False
        _validate_profile(path, installed)
    except JudgeError:
        return False
    return True


def _safe_extract(archive_path: Path, destination: Path) -> None:
    try:
        safe_extract_tar(archive_path, destination)
    except (OSError, tarfile.TarError) as exc:
        raise JudgeError(f"could not extract toolchain archive: {exc}") from exc


def _install_verified_archive(
    manifest: ToolchainManifest,
    archive_path: Path,
    *,
    root: Path,
    downloaded: bool,
) -> ToolchainInstallResult:
    if manifest.platform_id != current_platform_id():
        raise JudgeError(
            f"toolchain platform mismatch: {manifest.platform_id} != {current_platform_id()}"
        )
    if not archive_path.is_file() or _sha256_file(archive_path) != manifest.artifact.sha256:
        raise JudgeError("managed toolchain artifact hash mismatch")
    root.mkdir(parents=True, exist_ok=True)
    target = _profile_path(manifest, root)
    if _matching_installed_profile(target, manifest):
        _write_active_pointer(manifest, root)
        return ToolchainInstallResult(
            manifest.profile_id,
            manifest.version,
            target,
            reused=True,
            downloaded=downloaded,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_name(f".{target.name}.previous-{uuid.uuid4().hex}")
    replaced_previous = False
    with tempfile.TemporaryDirectory(prefix=".install-", dir=root) as temporary_name:
        staged = Path(temporary_name) / "profile"
        staged.mkdir()
        _safe_extract(archive_path, staged)
        _validate_profile(staged, manifest)
        (staged / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            if target.exists():
                os.replace(target, backup)
                replaced_previous = True
            os.replace(staged, target)
            _write_active_pointer(manifest, root)
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            if replaced_previous and backup.exists():
                os.replace(backup, target)
            raise
    if backup.exists():
        shutil.rmtree(backup)
    return ToolchainInstallResult(
        manifest.profile_id,
        manifest.version,
        target,
        reused=False,
        downloaded=downloaded,
    )


def install_toolchain_from_local_archive(
    manifest: ToolchainManifest,
    archive_path: Path,
    *,
    root: Path | None = None,
) -> ToolchainInstallResult:
    """Install a caller-provided, hash-verified archive without network access."""
    return _install_verified_archive(
        manifest,
        archive_path.resolve(),
        root=toolchain_root(root),
        downloaded=False,
    )


def ensure_managed_toolchain(
    manifest: ToolchainManifest,
    *,
    downloader: Callable[[str], Path] | None = None,
    root: Path | None = None,
) -> ToolchainInstallResult:
    """Reuse an installed profile or obtain it through an explicitly injected downloader."""
    managed_root = toolchain_root(root)
    target = _profile_path(manifest, managed_root)
    if _matching_installed_profile(target, manifest):
        _write_active_pointer(manifest, managed_root)
        return ToolchainInstallResult(
            manifest.profile_id,
            manifest.version,
            target,
            reused=True,
            downloaded=False,
        )
    if not manifest.provider_configured:
        raise JudgeError(
            "managed toolchain provider is not configured: URL, signature, and license "
            "must be approved before downloads are enabled"
        )
    if downloader is None:
        raise JudgeError("managed toolchain download transport is not configured")
    archive_path = downloader(manifest.artifact.url or "")
    return _install_verified_archive(
        manifest,
        archive_path.resolve(),
        root=managed_root,
        downloaded=True,
    )


def active_toolchain(root: Path | None = None) -> tuple[ToolchainManifest, Path] | None:
    managed_root = toolchain_root(root)
    pointer = _read_active_pointer(managed_root)
    if pointer is None:
        return None
    manifest_path = (
        managed_root / "profiles" / pointer["profileId"] / pointer["version"] / "manifest.json"
    )
    manifest = load_toolchain_manifest(manifest_path)
    if (
        manifest.profile_id != pointer["profileId"]
        or manifest.version != pointer["version"]
        or manifest.platform_id != pointer["platformId"]
    ):
        raise JudgeError("managed toolchain active pointer does not match its manifest")
    profile = manifest_path.parent
    _validate_profile(profile, manifest)
    return manifest, profile


def managed_provider_status(root: Path | None = None) -> dict[str, Any]:
    try:
        active = active_toolchain(root)
    except JudgeError as exc:
        return {"status": "invalid", "configured": False, "active": None, "error": str(exc)}
    if active is None:
        return {
            "status": "unconfigured",
            "configured": False,
            "active": None,
            "error": (
                "No approved managed toolchain provider manifest is configured. "
                "System PATH and ALJ_* overrides remain available."
            ),
        }
    manifest, profile = active
    return {
        "status": "ok",
        "configured": manifest.provider_configured,
        "active": {
            "profileId": manifest.profile_id,
            "version": manifest.version,
            "platformId": manifest.platform_id,
            "path": str(profile),
        },
        "error": None,
    }


def deactivate_managed_toolchain(root: Path | None = None) -> bool:
    """Atomically select system/override resolution by removing the active pointer."""
    pointer = _active_pointer_path(toolchain_root(root))
    if not pointer.exists():
        return False
    pointer.unlink()
    return True


def _external_executable(value: str) -> str | None:
    expanded = Path(value).expanduser()
    has_separator = os.sep in value or (os.altsep is not None and os.altsep in value)
    if expanded.is_absolute() or has_separator:
        resolved = expanded.resolve()
        return str(resolved) if resolved.is_file() and os.access(resolved, os.X_OK) else None
    resolved = shutil.which(value)
    return str(Path(resolved).resolve()) if resolved else None


def resolve_tool_details(
    tool_id: str,
    *,
    env_name: str | None = None,
    candidates: tuple[str, ...] | list[str] | None = None,
    root: Path | None = None,
) -> ResolvedTool:
    spec = TOOL_SPECS.get(tool_id)
    effective_env = env_name or (spec.env_name if spec else "")
    effective_candidates = tuple(candidates or (spec.candidates if spec else ()))
    configured = os.environ.get(effective_env) if effective_env else None
    if configured:
        resolved = _external_executable(configured)
        if resolved is None:
            raise JudgeError(f"configured tool is not executable: {effective_env}={configured}")
        return ResolvedTool(tool_id, resolved, "override", effective_env)

    active = active_toolchain(root)
    if active is not None:
        manifest, profile = active
        managed_tool = manifest.tools.get(tool_id)
        if managed_tool is not None:
            executable = (profile / PurePosixPath(managed_tool.path)).resolve()
            _validate_tool(executable, managed_tool.sha256, tool_id)
            return ResolvedTool(
                tool_id,
                str(executable),
                "managed",
                effective_env,
                manifest.profile_id,
                manifest.version,
            )

    for candidate in effective_candidates:
        resolved = _external_executable(candidate)
        if resolved is not None:
            return ResolvedTool(tool_id, resolved, "path", effective_env)
    hint = f"Set {effective_env} or " if effective_env else ""
    raise JudgeError(
        f"required tool not found. {hint}install one of: {', '.join(effective_candidates)}"
    )


def resolve_tool(env_name: str, candidates: list[str], root: Path | None = None) -> str:
    tool_id = next(
        (name for name, spec in TOOL_SPECS.items() if spec.env_name == env_name),
        env_name.lower().removeprefix("alj_"),
    )
    return resolve_tool_details(
        tool_id,
        env_name=env_name,
        candidates=candidates,
        root=root,
    ).path
