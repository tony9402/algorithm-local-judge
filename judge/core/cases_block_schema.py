"""cases_block_schema 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from judge.core.cases_diagnostics import (
    diagnostic,
    find_case_line,
    type_label,
)
from judge.core.cases_models import CaseCompileDiagnostic


def validate_case_block(
    path: Path,
    lines: list[str],
    profile: str,
    case: Any,
    case_index: int,
) -> list[CaseCompileDiagnostic]:
    """validate_case_block 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
        lines (list[str]): `lines` 값입니다.
        profile (str): `profile` 값입니다.
        case (Any): `case` 값입니다.
        case_index (int): `case_index` 값입니다.
    
    Returns:
        list[CaseCompileDiagnostic]: 처리 결과를 반환합니다.
    """
    line = find_case_line(lines, profile, case_index)
    location = f"cases[{case_index}]"
    if not isinstance(case, dict):
        return [
            diagnostic(
                path,
                f"case must be a mapping, got {type_label(case)}",
                line=line,
                profile=profile,
                location=location,
            )
        ]
    if "repeat" in case and "matrix" in case:
        return [
            diagnostic(
                path,
                "case must not define both repeat and matrix",
                line=line,
                profile=profile,
                location=location,
            )
        ]
    diagnostics = []
    if "matrix" in case and not isinstance(case["matrix"], dict):
        diagnostics.append(
            diagnostic(
                path,
                f"matrix must be a mapping, got {type_label(case['matrix'])}",
                line=line,
                profile=profile,
                location=f"{location}.matrix",
                hint="`vars`, `where`, and `item` must be indented under `matrix:`.",
            )
        )
    if "repeat" in case and not isinstance(case["repeat"], dict):
        diagnostics.append(
            diagnostic(
                path,
                f"repeat must be a mapping, got {type_label(case['repeat'])}",
                line=line,
                profile=profile,
                location=f"{location}.repeat",
                hint="repeat settings must be indented under `repeat:`.",
            )
        )
    return diagnostics
