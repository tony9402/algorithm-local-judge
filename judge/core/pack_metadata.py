from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge.core.pack_archive import reject_forbidden_release_file
from judge.core.problem import PRECOMPILED_TOOL_MODE
from judge.utils.hashing import sha256_file


@dataclass(frozen=True)
class PackBuildResult:
    """Result of creating a problem pack archive."""

    archive_path: Path
    pack_id: str
    platform_id: str
    problems: list[str]
    solution_checks: list[dict[str, object]]


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
