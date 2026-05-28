"""source_request 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import ensure_inside
from judge.web.source_history_paths import source_history_root
from judge.web.source_history_store import save_existing_source, save_text_source


def source_path_from_request(
    problem_id: str,
    source_mode: str,
    source_path: str | None,
    source_text: str | None,
    filename: str | None,
) -> Path:
    """source_path_from_request 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        source_mode (str): `source_mode` 값입니다.
        source_path (str | None): `source_path` 값입니다.
        source_text (str | None): `source_text` 값입니다.
        filename (str | None): `filename` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if source_mode == "path":
        if not source_path:
            raise JudgeError("source path is required")
        path = Path(source_path).expanduser()
        if not path.exists():
            raise JudgeError(f"source file not found: {path}")
        return save_existing_source(path, problem_id, "path")

    if source_mode == "upload":
        if not source_path:
            raise JudgeError("uploaded source path is required")
        path = Path(source_path)
        if not path.exists():
            raise JudgeError(f"uploaded source file not found: {path}")
        with contextlib.suppress(JudgeError):
            return ensure_inside(path, source_history_root())
        return save_existing_source(path, problem_id, "upload")

    if not source_text:
        raise JudgeError("source text is required")
    return save_text_source(source_text, filename, problem_id)
