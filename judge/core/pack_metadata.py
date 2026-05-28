"""pack_metadata 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
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
    """PackBuildResult 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    archive_path: Path
    pack_id: str
    platform_id: str
    problems: list[str]
    solution_checks: list[dict[str, object]]


def manifest_files(pack_dir: Path) -> list[dict[str, str]]:
    """manifest_files 함수를 실행하고 결과를 반환합니다.
    
    Args:
        pack_dir (Path): `pack_dir` 값입니다.
    
    Returns:
        list[dict[str, str]]: 처리 결과를 반환합니다.
    """
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
    """sanitize_problem_metadata 함수를 실행하고 결과를 반환합니다.
    
    Args:
        metadata (dict[str, Any]): `metadata` 값입니다.
        platform_id (str): `platform_id` 값입니다.
        suffix (str): `suffix` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
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
