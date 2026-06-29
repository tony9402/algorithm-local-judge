"""문제팩 메타데이터 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alj_core.pack_archive import reject_forbidden_release_file
from alj_core.problem import PRECOMPILED_TOOL_MODE
from alj_core.utils.hashing import sha256_file


@dataclass(frozen=True)
class PackBuildResult:
    """문제팩 build 결과에 필요한 필드를 한데 묶어 전달하는 데이터 모델입니다.
    """

    archive_path: Path
    pack_id: str
    platform_id: str
    problems: list[str]
    solution_checks: list[dict[str, object]]


def manifest_files(pack_dir: Path) -> list[dict[str, str]]:
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
