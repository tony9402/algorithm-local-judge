"""설정 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

import os
import re

PROTOCOL_VERSION = 1
COMPILE_FLAGS = ["-std=c++17", "-O2", "-pipe"]
ENV_TOOL_COMPILE_TIMEOUT_MIN_MS = "ALJ_TOOL_COMPILE_TIMEOUT_MIN_MS"
MAX_TOOL_COMPILE_TIMEOUT_FLOOR_MS = 120_000
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
FORBIDDEN_METADATA_KEYS = {
    "externalId",
    "externalUrl",
    "externalPlatform",
    "platform",
}


def effective_tool_compile_timeout_ms(configured: object, default: int = 5000) -> int:
    """Apply an optional bounded floor for slow container toolchain startup."""
    timeout_ms = (
        configured if isinstance(configured, int) and not isinstance(configured, bool) else default
    )
    raw_floor = os.environ.get(ENV_TOOL_COMPILE_TIMEOUT_MIN_MS)
    if raw_floor is None:
        return timeout_ms
    try:
        floor_ms = int(raw_floor)
    except ValueError:
        return timeout_ms
    floor_ms = min(MAX_TOOL_COMPILE_TIMEOUT_FLOOR_MS, max(0, floor_ms))
    return max(timeout_ms, floor_ms)
