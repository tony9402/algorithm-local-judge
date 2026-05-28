"""service_common 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
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
    """language_from_filename 함수를 실행하고 결과를 반환합니다.
    
    Args:
        filename (str): `filename` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    suffix = Path(filename).suffix.lower()
    if suffix in {".cpp", ".cc", ".cxx"}:
        return "C++"
    if suffix == ".py":
        return "Python"
    if suffix == ".java":
        return "Java"
    return "Unknown"


def web_debug_enabled() -> bool:
    """web_debug_enabled 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    value = os.environ.get(WEB_DEBUG_ENV, "")
    return value.lower() in {"1", "true", "yes", "on"}


def format_duration(milliseconds: int) -> str:
    """format_duration 함수를 실행하고 결과를 반환합니다.
    
    Args:
        milliseconds (int): `milliseconds` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    if milliseconds < 1000:
        return f"{milliseconds} ms"
    return f"{milliseconds / 1000:.2f} s"


def sse(event: str, data: dict[str, Any]) -> str:
    """sse 함수를 실행하고 결과를 반환합니다.
    
    Args:
        event (str): 발생한 이벤트입니다.
        data (dict[str, Any]): 처리할 데이터입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
