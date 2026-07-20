"""서비스 common 웹 백엔드 구성과 응답 데이터 조립을 담당합니다."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.languages import (
    LANGUAGE_OPTIONS,
    language_default_filename,
    language_display,
    language_extensions,
    language_id_from_filename,
    normalize_language_id,
)

SAMPLE_PROFILE = "sample"
HIDDEN_PROFILE = "hidden"
FULL_PROFILE = "full"
ARTIFACT_PREVIEW_LIMIT = 12000
SOURCE_HISTORY_LIMIT = 50
WEB_DEBUG_ENV = "ALJ_WEB_DEBUG"
SSE_DONE = object()


def normalize_submission_filename(
    filename: str | None,
    language: str | None = None,
    problem_id: str | None = None,
) -> str:
    raw_name = Path(filename).name if filename else ""
    if raw_name in {".", ".."}:
        raw_name = ""
    language_value = (language or "").strip()
    explicit_language = normalize_language_id(language)
    inferred_language = language_id_from_filename(raw_name) if raw_name else None
    if language_value and explicit_language is None:
        raise JudgeError(f"unsupported submission language: {language}")
    selected_language = explicit_language or inferred_language or "python"
    if selected_language not in LANGUAGE_OPTIONS:
        raise JudgeError(f"unsupported submission language: {language}")
    suffix = Path(raw_name).suffix.lower()
    if suffix and suffix not in language_extensions(selected_language):
        supported = ", ".join(
            sorted(
                extension for spec in LANGUAGE_OPTIONS.values() for extension in spec["extensions"]
            )
        )
        raise JudgeError(f"unsupported source extension: {suffix} (supported: {supported})")
    if raw_name:
        stem = raw_name
    else:
        stem = language_default_filename(selected_language)
    if Path(stem).suffix:
        return stem
    default_name = language_default_filename(selected_language)
    extension = Path(default_name).suffix
    if not stem:
        base = f"main-{problem_id}" if problem_id else Path(default_name).stem
        return f"{base}{extension}"
    return f"{stem}{extension}"


def language_from_filename(filename: str) -> str:
    return language_display(language_id_from_filename(filename))


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
