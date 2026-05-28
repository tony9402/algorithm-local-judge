"""소스 이력 경로 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
"""
from __future__ import annotations

import contextlib
import time
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import cache_root, ensure_inside, validate_safe_id


def source_history_root() -> Path:
    return cache_root() / "web-submissions"


def source_entry_dir(source_id: str) -> Path:
    validate_safe_id("source id", source_id)
    return ensure_inside(source_history_root() / source_id, cache_root())


def default_filename(problem_id: str, filename: str | None) -> str:
    if filename:
        name = Path(filename).name
    else:
        name = f"main-{problem_id}.py"
    if not name or name in {".", ".."}:
        raise JudgeError("invalid source filename")
    return name


def create_source_target(problem_id: str, filename: str | None) -> tuple[str, Path]:
    """소스 target 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        filename (str | None): 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.

    Returns:
        tuple[str, Path]: 검증된 소스 target 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    validate_safe_id("problem id", problem_id)
    source_id = str(time.time_ns())
    target_dir = source_entry_dir(source_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    return source_id, target_dir / default_filename(problem_id, filename)


def source_id_from_path(source: Path) -> str | None:
    with contextlib.suppress(JudgeError):
        cached_source = ensure_inside(source, source_history_root())
        if cached_source.parent.parent == source_history_root():
            return cached_source.parent.name
    return None
