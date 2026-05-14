from __future__ import annotations

import copy
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge import __version__
from judge.core.compiler import compile_problem_tools
from judge.core.errors import JudgeError
from judge.core.paths import (
    current_platform_id,
    executable_suffix,
    problem_pack_root,
    repo_root,
    validate_safe_id,
)
from judge.core.problem import PRECOMPILED_TOOL_MODE, TOOL_NAMES, load_problem, tool_paths
from judge.utils.fs import read_json, write_json
from judge.utils.hashing import sha256_file

FORBIDDEN_PACK_SUFFIXES = {
    ".cpp",
    ".cc",
    ".cxx",
    ".hpp",
    ".hh",
    ".hxx",
    ".h",
    ".pdb",
    ".o",
    ".obj",
    ".a",
    ".lib",
}
FORBIDDEN_PACK_NAMES = {".dsym"}
PACK_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PackBuildResult:
    """Result of creating a problem pack archive."""

    archive_path: Path
    pack_id: str
    platform_id: str
    problems: list[str]


def reject_forbidden_release_file(path: Path) -> None:
    """Reject source or debug artifacts that must not be released in packs."""
    lowered_name = path.name.lower()
    if path.suffix.lower() in FORBIDDEN_PACK_SUFFIXES or lowered_name in FORBIDDEN_PACK_NAMES:
        raise JudgeError(f"forbidden file in problem pack: {path}")


def safe_tar_members(archive_path: Path) -> list[tarfile.TarInfo]:
    """Return tar members after checking for absolute or parent-traversal paths."""
    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
    for member in members:
        member_path = Path(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise JudgeError(f"unsafe path in pack archive: {member.name}")
    return members


def safe_extract_tar(archive_path: Path, target_dir: Path) -> None:
    """Extract a tar archive after validating member paths."""
    members = safe_tar_members(archive_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:*") as archive:
        archive.extractall(target_dir, members=members)


def single_pack_dir(extracted_dir: Path) -> Path:
    """Return the single top-level pack directory from an extracted archive."""
    candidates = [path for path in extracted_dir.iterdir() if path.is_dir()]
    if len(candidates) != 1:
        raise JudgeError("pack archive must contain exactly one top-level directory")
    return candidates[0]


def manifest_files(pack_dir: Path) -> list[dict[str, str]]:
    """Build file hash entries for all files in a staged pack directory."""
    files = []
    for path in sorted(item for item in pack_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(pack_dir).as_posix()
        if relative == "manifest.json":
            continue
        reject_forbidden_release_file(path)
        files.append({"path": relative, "sha256": sha256_file(path)})
    return files


def verify_pack_dir(pack_dir: Path) -> dict[str, Any]:
    """Validate an extracted problem pack directory and return pack metadata."""
    pack_json = pack_dir / "pack.json"
    manifest_json = pack_dir / "manifest.json"
    if not pack_json.exists():
        raise JudgeError("pack.json not found in problem pack")
    if not manifest_json.exists():
        raise JudgeError("manifest.json not found in problem pack")
    pack = read_json(pack_json)
    manifest = read_json(manifest_json)
    if pack.get("schemaVersion") != PACK_SCHEMA_VERSION:
        raise JudgeError(f"unsupported pack schema version: {pack.get('schemaVersion')}")
    if manifest.get("schemaVersion") != PACK_SCHEMA_VERSION:
        raise JudgeError(f"unsupported manifest schema version: {manifest.get('schemaVersion')}")
    validate_safe_id("pack id", pack.get("packId", ""))
    for path in pack_dir.rglob("*"):
        if path.is_file():
            reject_forbidden_release_file(path)
    expected_files = {entry["path"]: entry["sha256"] for entry in manifest.get("files", [])}
    if not expected_files:
        raise JudgeError("problem pack manifest has no file entries")
    for relative, expected_hash in expected_files.items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise JudgeError(f"unsafe path in pack manifest: {relative}")
        path = pack_dir / relative
        if not path.exists():
            raise JudgeError(f"manifest file missing: {relative}")
        if sha256_file(path) != expected_hash:
            raise JudgeError(f"manifest hash mismatch: {relative}")
    return pack


def verify_pack(archive_path: Path) -> dict[str, Any]:
    """Validate a problem pack archive and return pack metadata."""
    archive_path = archive_path.resolve()
    if not archive_path.exists():
        raise JudgeError(f"problem pack not found: {archive_path}")
    with tempfile.TemporaryDirectory(prefix="alj-pack-verify-") as tmp:
        extracted_dir = Path(tmp)
        safe_extract_tar(archive_path, extracted_dir)
        return verify_pack_dir(single_pack_dir(extracted_dir))


def sanitize_problem_metadata(
    metadata: dict[str, Any],
    platform_id: str,
    suffix: str,
) -> dict[str, Any]:
    """Return problem metadata that points at precompiled pack tools."""
    sanitized = copy.deepcopy(metadata)
    sanitized["tools"] = {
        "mode": PRECOMPILED_TOOL_MODE,
        "generatorConfig": "generator/cases.yml",
        "generator": f"compiled-tools/{platform_id}/generator{suffix}",
        "validator": f"compiled-tools/{platform_id}/validator{suffix}",
        "checker": f"compiled-tools/{platform_id}/checker{suffix}",
        "solution": f"compiled-tools/{platform_id}/solution{suffix}",
    }
    return sanitized


def copy_problem_into_pack(
    problem_id: str,
    pack_problem_dir: Path,
    platform_id: str,
    root: Path | None = None,
) -> None:
    """Copy one development problem into a staged source-free pack directory."""
    problem_dir, _, metadata, paths = tool_paths(problem_id, root)
    tools = compile_problem_tools(problem_id, root)
    suffix = executable_suffix()
    pack_problem_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        pack_problem_dir / "problem.json", sanitize_problem_metadata(metadata, platform_id, suffix)
    )
    config_target = pack_problem_dir / "generator" / "cases.yml"
    config_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths["generatorConfig"], config_target)
    tool_target_dir = pack_problem_dir / "compiled-tools" / platform_id
    tool_target_dir.mkdir(parents=True, exist_ok=True)
    for name in TOOL_NAMES:
        target = tool_target_dir / f"{name}{suffix}"
        shutil.copy2(tools[name], target)
        target.chmod(target.stat().st_mode | 0o755)
    if problem_dir == pack_problem_dir:
        raise JudgeError("refusing to pack a problem into itself")


def build_pack(
    problem_path: Path,
    pack_id: str,
    platform_id: str | None = None,
    output_dir: Path | None = None,
) -> PackBuildResult:
    """Build a source-free problem pack archive for one problem."""
    validate_safe_id("pack id", pack_id)
    problem_path = problem_path.resolve()
    if not (problem_path / "problem.json").exists():
        raise JudgeError(f"problem metadata not found: {problem_path / 'problem.json'}")
    platform_id = platform_id or current_platform_id()
    if platform_id != current_platform_id():
        raise JudgeError(
            "cross-platform pack build is not implemented yet; "
            f"current platform is {current_platform_id()}, requested {platform_id}"
        )
    problem_id = problem_path.name
    root = problem_path.parent.parent if problem_path.parent.name == "problems" else repo_root()
    _, _, metadata = load_problem(problem_id, root)
    version = str(metadata.get("version", __version__))
    output_dir = output_dir or repo_root() / "dist" / "packs"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{pack_id}-{version}-{platform_id}.aljpack"

    with tempfile.TemporaryDirectory(prefix="alj-pack-build-") as tmp:
        stage = Path(tmp) / pack_id
        write_json(
            stage / "pack.json",
            {
                "schemaVersion": PACK_SCHEMA_VERSION,
                "packId": pack_id,
                "name": f"{pack_id} problem pack",
                "version": version,
                "engineVersion": __version__,
                "supportedPlatforms": [platform_id],
                "problems": [problem_id],
            },
        )
        copy_problem_into_pack(problem_id, stage / "problems" / problem_id, platform_id, root)
        write_json(
            stage / "manifest.json",
            {
                "schemaVersion": PACK_SCHEMA_VERSION,
                "packId": pack_id,
                "version": version,
                "platformId": platform_id,
                "files": manifest_files(stage),
            },
        )
        verify_pack_dir(stage)
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(stage, arcname=pack_id)
    return PackBuildResult(archive_path, pack_id, platform_id, [problem_id])


def install_pack(archive_path: Path) -> Path:
    """Install a verified problem pack into the user data directory."""
    archive_path = archive_path.resolve()
    with tempfile.TemporaryDirectory(prefix="alj-pack-install-") as tmp:
        extracted_dir = Path(tmp)
        safe_extract_tar(archive_path, extracted_dir)
        staged_pack_dir = single_pack_dir(extracted_dir)
        pack = verify_pack_dir(staged_pack_dir)
        target = problem_pack_root() / pack["packId"]
        backup = None
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = target.with_name(target.name + ".old")
            if backup.exists():
                shutil.rmtree(backup)
            target.rename(backup)
        shutil.copytree(staged_pack_dir, target)
        if backup is not None:
            shutil.rmtree(backup)
        return target


def installed_packs() -> list[dict[str, Any]]:
    """Return metadata for installed problem packs."""
    root = problem_pack_root()
    if not root.exists():
        return []
    packs = []
    for pack_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        pack_json = pack_dir / "pack.json"
        if pack_json.exists():
            pack = read_json(pack_json)
            pack["path"] = str(pack_dir)
            packs.append(pack)
    return packs


def remove_pack(pack_id: str) -> Path:
    """Remove an installed problem pack by id."""
    validate_safe_id("pack id", pack_id)
    target = problem_pack_root() / pack_id
    if not target.exists():
        raise JudgeError(f"problem pack not installed: {pack_id}")
    shutil.rmtree(target)
    return target
