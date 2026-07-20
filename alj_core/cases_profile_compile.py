"""케이스 프로필 컴파일 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alj_core.cases_diagnostics import diagnostic, find_profile_line
from alj_core.cases_expansion import expand_profile_cases
from alj_core.cases_models import (
    CaseCompileDiagnostic,
    CompiledProfile,
)
from alj_core.cases_schema import validate_case_block, validate_concrete_case


def compile_profile(
    path: Path,
    lines: list[str],
    profile: str,
    profile_config: Any,
) -> tuple[CompiledProfile | None, list[CaseCompileDiagnostic]]:
    """프로필 소스와 설정을 실행 가능한 산출물과 진단 정보로 변환합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
        lines (list[str]): 프로필을 계산하거나 검증할 때 필요한 lines 입력입니다.
        profile (str): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        profile_config (Any): 프로필을 계산하거나 검증할 때 필요한 프로필 설정 입력입니다.

    Returns:
        tuple[CompiledProfile | None, list[CaseCompileDiagnostic]]: 호출자가 순회하거나 화면에 표시할 프로필 항목 목록입니다.
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
