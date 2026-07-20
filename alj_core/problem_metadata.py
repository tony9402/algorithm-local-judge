"""문제 메타데이터 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alj_core.config import FORBIDDEN_METADATA_KEYS
from alj_core.errors import JudgeError
from alj_core.paths import build_root, rel, repo_root, validate_safe_id
from alj_core.problem_constants import PRECOMPILED_TOOL_MODE, REQUIRED_TOOL_FIELDS
from alj_core.problem_discovery import find_problem_dir
from alj_core.utils.fs import read_json


def forbidden_metadata_keys(metadata: dict[str, Any]) -> set[str]:
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
    """문제을 파일이나 캐시에서 읽고 필요한 기본값을 적용합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.

    Returns:
        tuple[Path, Path, dict[str, Any]]: 검증된 문제 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
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
    """precompiled 문제 여부를 실제 파일, 설정, 또는 런타임 상태를 기준으로 판정합니다.

    Args:
        metadata (dict[str, Any]): 문제, 소스, 실행 결과에 붙는 제목, 제한, 경로 같은 부가 정보입니다.

    Returns:
        bool: precompiled 문제 조건을 만족하면 True, 아니면 False입니다.
    """
    tools = metadata.get("tools", {})
    return tools.get("mode") == PRECOMPILED_TOOL_MODE


def tool_paths(
    problem_id: str, root: Path | None = None
) -> tuple[Path, Path, dict[str, Any], dict[str, Path]]:
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
    return build_root(root) / "tools" / problem_id / name
