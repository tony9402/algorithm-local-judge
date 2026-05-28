"""cases_expansion 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from commons.generate import expand_cases
from judge.core.cases_diagnostics import (
    diagnostic,
    expansion_error_location,
    find_case_line,
)
from judge.core.cases_models import CaseCompileDiagnostic


def expand_profile_cases(
    path: Path,
    lines: list[str],
    profile: str,
    cases: list[Any],
) -> tuple[list[dict[str, Any]], list[CaseCompileDiagnostic]]:
    """expand_profile_cases 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
        lines (list[str]): `lines` 값입니다.
        profile (str): `profile` 값입니다.
        cases (list[Any]): `cases` 값입니다.
    
    Returns:
        tuple[list[dict[str, Any]], list[CaseCompileDiagnostic]]: 처리 결과를 반환합니다.
    """
    expanded: list[dict[str, Any]] = []
    diagnostics: list[CaseCompileDiagnostic] = []
    for index, case in enumerate(cases):
        try:
            expanded.extend(expand_cases([case]))
        except Exception as exc:
            message = str(exc)
            diagnostics.append(
                diagnostic(
                    path,
                    message,
                    line=find_case_line(lines, profile, index),
                    profile=profile,
                    location=expansion_error_location(case, f"cases[{index}]", message),
                )
            )
    return expanded, diagnostics
