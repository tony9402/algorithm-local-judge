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
    """Return a display language from a source filename."""
    suffix = Path(filename).suffix.lower()
    if suffix in {".cpp", ".cc", ".cxx"}:
        return "C++"
    if suffix == ".py":
        return "Python"
    if suffix == ".java":
        return "Java"
    return "Unknown"


def web_debug_enabled() -> bool:
    """Return whether the web UI should expose debug logs."""
    value = os.environ.get(WEB_DEBUG_ENV, "")
    return value.lower() in {"1", "true", "yes", "on"}


def format_duration(milliseconds: int) -> str:
    """Format a millisecond duration for web status summaries."""
    if milliseconds < 1000:
        return f"{milliseconds} ms"
    return f"{milliseconds / 1000:.2f} s"


def sse(event: str, data: dict[str, Any]) -> str:
    """Format one Server-Sent Events block."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
