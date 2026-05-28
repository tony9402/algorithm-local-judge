from __future__ import annotations

import tarfile
import tempfile
from pathlib import Path

from judge import __version__
from judge.core.checksums import write_sha256_sidecar
from judge.core.errors import JudgeError
from judge.core.pack_archive import PACK_SCHEMA_VERSION
from judge.core.pack_copy import copy_problem_into_pack
from judge.core.pack_metadata import (
    PackBuildResult,
    manifest_files,
    sanitize_problem_metadata,
)
from judge.core.pack_verify import verify_pack_dir
from judge.core.paths import current_platform_id, repo_root, validate_safe_id
from judge.core.problem import load_problem
from judge.core.solution_validation import verify_problem_solutions
from judge.utils.fs import write_json

__all__ = [
    "PackBuildResult",
    "build_pack",
    "build_pack_for_problem_ids",
    "copy_problem_into_pack",
    "manifest_files",
    "sanitize_problem_metadata",
    "write_pack_checksum",
]


def write_pack_checksum(archive_path: Path) -> Path:
    """Write the sidecar SHA-256 checksum expected next to release pack assets."""
    return write_sha256_sidecar(archive_path)


def build_pack(
    problem_path: Path,
    pack_id: str,
    platform_id: str | None = None,
    output_dir: Path | None = None,
    verify_profile: str = "hidden",
    warmup_profile: str | None = None,
) -> PackBuildResult:
    """Build a source-free problem pack archive for one problem."""
    problem_path = problem_path.resolve()
    if not (problem_path / "problem.json").exists():
        raise JudgeError(f"problem metadata not found: {problem_path / 'problem.json'}")
    problem_id = problem_path.name
    root = problem_path.parent.parent if problem_path.parent.name == "problems" else repo_root()
    return build_pack_for_problem_ids(
        [problem_id],
        pack_id,
        platform_id,
        output_dir,
        root,
        verify_profile,
        warmup_profile=warmup_profile,
    )


def build_pack_for_problem_ids(
    problem_ids: list[str],
    pack_id: str,
    platform_id: str | None = None,
    output_dir: Path | None = None,
    root: Path | None = None,
    verify_profile: str = "hidden",
    solution_checks: list[dict[str, object]] | None = None,
    warmup_profile: str | None = None,
) -> PackBuildResult:
    """Build one source-free problem pack archive containing multiple problems."""
    validate_safe_id("pack id", pack_id)
    if not problem_ids:
        raise JudgeError("problem pack must contain at least one problem")
    root = root or repo_root()
    normalized_problem_ids = []
    for problem_id in problem_ids:
        validate_safe_id("problem id", problem_id)
        if problem_id not in normalized_problem_ids:
            normalized_problem_ids.append(problem_id)
    platform_id = platform_id or current_platform_id()
    if platform_id != current_platform_id():
        raise JudgeError(
            "cross-platform pack build is not implemented yet; "
            f"current platform is {current_platform_id()}, requested {platform_id}"
        )
    metadata_by_problem = {
        problem_id: load_problem(problem_id, root)[2] for problem_id in normalized_problem_ids
    }
    version = (
        str(next(iter(metadata_by_problem.values())).get("version", __version__))
        if len(normalized_problem_ids) == 1
        else __version__
    )
    if solution_checks is None:
        solution_checks = []
        for problem_id in normalized_problem_ids:
            solution_verification = verify_problem_solutions(
                problem_id,
                verify_profile,
                root,
                warmup_profile=warmup_profile,
            )
            solution_checks.extend(check.to_dict(root) for check in solution_verification.checks)
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
                "problems": normalized_problem_ids,
            },
        )
        for problem_id in normalized_problem_ids:
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
    write_pack_checksum(archive_path)
    return PackBuildResult(
        archive_path,
        pack_id,
        platform_id,
        normalized_problem_ids,
        solution_checks,
    )
