"""source_history_paths 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import contextlib
import time
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import cache_root, ensure_inside, validate_safe_id


def source_history_root() -> Path:
    """source_history_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    return cache_root() / "web-submissions"


def source_entry_dir(source_id: str) -> Path:
    """source_entry_dir 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source_id (str): 소스 ID입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    validate_safe_id("source id", source_id)
    return ensure_inside(source_history_root() / source_id, cache_root())


def default_filename(problem_id: str, filename: str | None) -> str:
    """default_filename 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        filename (str | None): `filename` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    if filename:
        name = Path(filename).name
    else:
        name = f"main-{problem_id}.py"
    if not name or name in {".", ".."}:
        raise JudgeError("invalid source filename")
    return name


def create_source_target(problem_id: str, filename: str | None) -> tuple[str, Path]:
    """create_source_target 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        filename (str | None): `filename` 값입니다.
    
    Returns:
        tuple[str, Path]: 처리 결과를 반환합니다.
    """
    validate_safe_id("problem id", problem_id)
    source_id = str(time.time_ns())
    target_dir = source_entry_dir(source_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    return source_id, target_dir / default_filename(problem_id, filename)


def source_id_from_path(source: Path) -> str | None:
    """source_id_from_path 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (Path): `source` 값입니다.
    
    Returns:
        str | None: 처리 결과를 반환합니다.
    """
    with contextlib.suppress(JudgeError):
        cached_source = ensure_inside(source, source_history_root())
        if cached_source.parent.parent == source_history_root():
            return cached_source.parent.name
    return None
