"""problem_metadata 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from judge.core.config import FORBIDDEN_METADATA_KEYS
from judge.core.errors import JudgeError
from judge.core.paths import build_root, rel, repo_root, validate_safe_id
from judge.core.problem_constants import PRECOMPILED_TOOL_MODE, REQUIRED_TOOL_FIELDS
from judge.core.problem_discovery import find_problem_dir
from judge.utils.fs import read_json


def forbidden_metadata_keys(metadata: dict[str, Any]) -> set[str]:
    """forbidden_metadata_keys 함수를 실행하고 결과를 반환합니다.
    
    Args:
        metadata (dict[str, Any]): `metadata` 값입니다.
    
    Returns:
        set[str]: 처리 결과를 반환합니다.
    """
    forbidden = set()
    for key in metadata:
        lowered = key.lower()
        if key in FORBIDDEN_METADATA_KEYS:
            forbidden.add(key)
        elif key != "problemId" and (
            lowered.endswith("id") or "platform" in lowered or "url" in lowered
        ):
            forbidden.add(key)
    return forbidden


def load_problem(problem_id: str, root: Path | None = None) -> tuple[Path, Path, dict[str, Any]]:
    """load_problem 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        tuple[Path, Path, dict[str, Any]]: 처리 결과를 반환합니다.
    """
    validate_safe_id("problem id", problem_id)
    problem_dir = find_problem_dir(problem_id, root)
    display_root = root or repo_root()
    metadata_path = problem_dir / "problem.json"
    if not metadata_path.exists():
        raise JudgeError(f"problem metadata not found: {rel(metadata_path, display_root)}")
    metadata = read_json(metadata_path)
    forbidden = sorted(forbidden_metadata_keys(metadata))
    if forbidden:
        path_label = rel(metadata_path, display_root)
        raise JudgeError(f"forbidden metadata keys in {path_label}: {', '.join(forbidden)}")
    if metadata.get("problemId") != problem_id:
        raise JudgeError(f"problemId mismatch in {rel(metadata_path, display_root)}")
    return problem_dir, metadata_path, metadata


def is_precompiled_problem(metadata: dict[str, Any]) -> bool:
    """is_precompiled_problem 함수를 실행하고 결과를 반환합니다.
    
    Args:
        metadata (dict[str, Any]): `metadata` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    tools = metadata.get("tools", {})
    return tools.get("mode") == PRECOMPILED_TOOL_MODE


def tool_paths(
    problem_id: str, root: Path | None = None
) -> tuple[Path, Path, dict[str, Any], dict[str, Path]]:
    """tool_paths 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        tuple[Path, Path, dict[str, Any], dict[str, Path]]: 처리 결과를 반환합니다.
    """
    display_root = root or repo_root()
    problem_dir, metadata_path, metadata = load_problem(problem_id, root)
    tools = metadata.get("tools", {})
    missing = [name for name in REQUIRED_TOOL_FIELDS if name not in tools]
    if missing:
        raise JudgeError(f"missing tool path(s): {', '.join(missing)}")
    paths = {}
    problem_root = problem_dir.resolve()
    for name in REQUIRED_TOOL_FIELDS:
        raw_path = Path(tools[name])
        if raw_path.is_absolute() or ".." in raw_path.parts:
            raise JudgeError(f"unsafe {name} path in metadata: {tools[name]}")
        path = (problem_dir / raw_path).resolve()
        if not (path == problem_root or problem_root in path.parents):
            raise JudgeError(f"{name} path escapes problem directory: {tools[name]}")
        paths[name] = path
    for name, path in paths.items():
        if not path.exists():
            raise JudgeError(f"{name} not found: {rel(path, display_root)}")
    return problem_dir, metadata_path, metadata, paths


def tool_output_path(problem_id: str, name: str, root: Path | None = None) -> Path:
    """tool_output_path 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        name (str): 이름입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    return build_root(root) / "tools" / problem_id / name
