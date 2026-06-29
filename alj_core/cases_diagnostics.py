"""케이스 진단 정보 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from alj_core.cases_models import CaseCompileDiagnostic
from alj_core.paths import rel

SAFE_CASE_NAME_RE = r"^[A-Za-z0-9_.-]+$"
VARIABLE_MESSAGE_PREFIX = "unknown variable: "


def diagnostic(
    path: Path,
    message: str,
    *,
    line: int | None = None,
    profile: str | None = None,
    location: str = "",
    hint: str | None = None,
) -> CaseCompileDiagnostic:
    return CaseCompileDiagnostic(
        severity="error",
        path=rel(path),
        line=line,
        profile=profile,
        location=location,
        message=message,
        hint=hint,
    )


def type_label(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def is_integer(value: Any) -> bool:
    """integer 여부를 실제 파일, 설정, 또는 런타임 상태를 기준으로 판정합니다.

    Args:
        value (Any): 검증하거나 상태에 반영할 입력 값입니다.

    Returns:
        bool: integer 조건을 만족하면 True, 아니면 False입니다.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def find_profile_line(lines: list[str], profile: str) -> int | None:
    target = f"{profile}:"
    for index, line in enumerate(lines, start=1):
        if line_indent(line) == 2 and line.strip() == target:
            return index
    return None


def profile_bounds(lines: list[str], profile: str) -> tuple[int, int] | None:
    start = None
    for index, line in enumerate(lines):
        if line_indent(line) == 2 and line.strip() == f"{profile}:":
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped and line_indent(lines[index]) == 2 and stripped.endswith(":"):
            end = index
            break
    return start, end


def find_case_line(lines: list[str], profile: str, case_index: int) -> int | None:
    bounds = profile_bounds(lines, profile)
    if bounds is None:
        return None
    seen = -1
    for index in range(bounds[0], bounds[1]):
        if line_indent(lines[index]) == 6 and lines[index].strip().startswith("- "):
            seen += 1
            if seen == case_index:
                return index + 1
    return None


def location_part(key: str | int) -> str:
    if isinstance(key, int):
        return f"[{key}]"
    if re.fullmatch(SAFE_CASE_NAME_RE, key):
        return f".{key}"
    return f"[{key!r}]"


def expression_mentions_variable(value: str, variable: str) -> bool:
    return "${" in value and re.search(rf"\b{re.escape(variable)}\b", value) is not None


def find_variable_reference_location(value: Any, variable: str) -> str | None:
    if isinstance(value, str):
        return "" if expression_mentions_variable(value, variable) else None
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = find_variable_reference_location(child, variable)
            if child_location is not None:
                return location_part(str(key)) + child_location
    if isinstance(value, list):
        for index, child in enumerate(value):
            child_location = find_variable_reference_location(child, variable)
            if child_location is not None:
                return location_part(index) + child_location
    return None


def expansion_error_location(case: Any, base_location: str, message: str) -> str:
    if not isinstance(case, dict):
        return base_location
    if "matrix" in case:
        return matrix_error_location(case["matrix"], base_location, message)
    if "repeat" in case:
        return repeat_error_location(case["repeat"], base_location, message)
    return base_location


def matrix_error_location(block: Any, base_location: str, message: str) -> str:
    matrix_location = f"{base_location}.matrix"
    if not isinstance(block, dict):
        return matrix_location
    if message.startswith(VARIABLE_MESSAGE_PREFIX):
        variable = message.removeprefix(VARIABLE_MESSAGE_PREFIX)
        where = block.get("where")
        if isinstance(where, str) and re.search(rf"\b{re.escape(variable)}\b", where):
            return f"{matrix_location}.where"
        for key in ("item", "items", "vars"):
            if key in block:
                child_location = find_variable_reference_location(block[key], variable)
                if child_location is not None:
                    return f"{matrix_location}.{key}{child_location}"
    if message.startswith("matrix.vars"):
        return f"{matrix_location}.vars"
    if message.startswith("matrix variable"):
        return f"{matrix_location}.vars"
    return matrix_location


def repeat_error_location(block: Any, base_location: str, message: str) -> str:
    repeat_location = f"{base_location}.repeat"
    if not isinstance(block, dict):
        return repeat_location
    if message.startswith(VARIABLE_MESSAGE_PREFIX):
        variable = message.removeprefix(VARIABLE_MESSAGE_PREFIX)
        for key in ("item", "items", "in", "from", "to", "step"):
            if key in block:
                child_location = find_variable_reference_location(block[key], variable)
                if child_location is not None:
                    return f"{repeat_location}.{key}{child_location}"
    if message.startswith("invalid variable name") or message.startswith("variable name"):
        return f"{repeat_location}.var"
    return repeat_location
