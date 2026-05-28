"""서비스 common 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SAMPLE_PROFILE = "sample"
HIDDEN_PROFILE = "hidden"
FULL_PROFILE = "full"
ARTIFACT_PREVIEW_LIMIT = 12000
SOURCE_HISTORY_LIMIT = 50
WEB_DEBUG_ENV = "ALJ_WEB_DEBUG"
SSE_DONE = object()


def language_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".cpp", ".cc", ".cxx"}:
        return "C++"
    if suffix == ".py":
        return "Python"
    if suffix == ".java":
        return "Java"
    return "Unknown"


def web_debug_enabled() -> bool:
    value = os.environ.get(WEB_DEBUG_ENV, "")
    return value.lower() in {"1", "true", "yes", "on"}


def format_duration(milliseconds: int) -> str:
    """기간 데이터를 CLI나 UI에 표시할 문자열로 변환합니다.

    Args:
        milliseconds (int): 기간을 계산하거나 검증할 때 필요한 milliseconds 입력입니다.

    Returns:
        str: 콘솔, 로그, 또는 이벤트 스트림에 바로 쓸 수 있는 문자열입니다.
    """
    if milliseconds < 1000:
        return f"{milliseconds} ms"
    return f"{milliseconds / 1000:.2f} s"


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
