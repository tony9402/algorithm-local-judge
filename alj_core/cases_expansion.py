"""케이스 expansion 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from commons.generate import expand_cases
from alj_core.cases_diagnostics import (
    diagnostic,
    expansion_error_location,
    find_case_line,
)
from alj_core.cases_models import CaseCompileDiagnostic


def expand_profile_cases(
    path: Path,
    lines: list[str],
    profile: str,
    cases: list[Any],
) -> tuple[list[dict[str, Any]], list[CaseCompileDiagnostic]]:
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
