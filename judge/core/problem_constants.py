"""problem_constants 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

TOOL_NAMES = ["generator", "validator", "checker", "solution"]
REQUIRED_TOOL_FIELDS = [*TOOL_NAMES, "generatorConfig"]
PRECOMPILED_TOOL_MODE = "precompiled"
