"""cases_profile_compile 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from judge.core.cases_diagnostics import diagnostic, find_profile_line
from judge.core.cases_expansion import expand_profile_cases
from judge.core.cases_models import (
    CaseCompileDiagnostic,
    CompiledProfile,
)
from judge.core.cases_schema import validate_case_block, validate_concrete_case


def compile_profile(
    path: Path,
    lines: list[str],
    profile: str,
    profile_config: Any,
) -> tuple[CompiledProfile | None, list[CaseCompileDiagnostic]]:
    """compile_profile 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
        lines (list[str]): `lines` 값입니다.
        profile (str): `profile` 값입니다.
        profile_config (Any): `profile_config` 값입니다.
    
    Returns:
        tuple[CompiledProfile | None, list[CaseCompileDiagnostic]]: 처리 결과를 반환합니다.
    """
    line = find_profile_line(lines, profile)
    if not isinstance(profile_config, dict):
        return None, [
            diagnostic(
                path,
                "profile must be a mapping",
                line=line,
                profile=profile,
                location=f"profiles.{profile}",
            )
        ]
    cases = profile_config.get("cases")
    if not isinstance(cases, list):
        return None, [
            diagnostic(
                path,
                "profile cases must be a list",
                line=line,
                profile=profile,
                location=f"profiles.{profile}.cases",
            )
        ]
    diagnostics = []
    for index, case in enumerate(cases):
        diagnostics.extend(validate_case_block(path, lines, profile, case, index))
    if diagnostics:
        return None, diagnostics
    expanded, expansion_diagnostics = expand_profile_cases(path, lines, profile, cases)
    if expansion_diagnostics:
        return None, expansion_diagnostics
    if not expanded:
        return None, [
            diagnostic(
                path,
                "profile produced no cases",
                line=line,
                profile=profile,
                location=f"profiles.{profile}.cases",
            )
        ]
    compiled_cases = []
    seen_names: set[str] = set()
    for index, case in enumerate(expanded, start=1):
        compiled_case, case_diagnostics = validate_concrete_case(
            path, profile, case, index, seen_names
        )
        diagnostics.extend(case_diagnostics)
        if compiled_case is not None:
            compiled_cases.append(compiled_case)
    if diagnostics:
        return None, diagnostics
    return CompiledProfile(profile, compiled_cases), []
