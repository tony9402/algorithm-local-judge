"""텍스트 기능을 담당하는 모듈입니다.
"""
from __future__ import annotations

from pathlib import Path


def format_size(size: int) -> str:
    """size 데이터를 CLI나 UI에 표시할 문자열로 변환합니다.

    Args:
        size (int): size을 계산하거나 검증할 때 필요한 size 입력입니다.

    Returns:
        str: 콘솔, 로그, 또는 이벤트 스트림에 바로 쓸 수 있는 문자열입니다.
    """
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024


def preview(path: Path, max_chars: int = 4000) -> str:
    """미리보기 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
        max_chars (int): 미리보기을 계산하거나 검증할 때 필요한 max chars 입력입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 미리보기 문자열입니다.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n... truncated ...\n"
    return text
