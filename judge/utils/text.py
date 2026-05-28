"""text 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path


def format_size(size: int) -> str:
    """format_size 함수를 실행하고 결과를 반환합니다.
    
    Args:
        size (int): `size` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024


def preview(path: Path, max_chars: int = 4000) -> str:
    """preview 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
        max_chars (int): `max_chars` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n... truncated ...\n"
    return text
