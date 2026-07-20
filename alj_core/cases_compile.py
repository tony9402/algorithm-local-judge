"""케이스 컴파일 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

from pathlib import Path

from alj_core.cases_diagnostics import (
    SAFE_CASE_NAME_RE,
    VARIABLE_MESSAGE_PREFIX,
    diagnostic,
    expansion_error_location,
    expression_mentions_variable,
    find_case_line,
    find_profile_line,
    find_variable_reference_location,
    is_integer,
    line_indent,
    location_part,
    matrix_error_location,
    profile_bounds,
    repeat_error_location,
    type_label,
)
from alj_core.cases_expansion import expand_profile_cases
from alj_core.cases_format import format_compile_result, format_diagnostic, result_to_json
from alj_core.cases_io import load_yaml
from alj_core.cases_models import (
    CaseCompileDiagnostic,
    CaseCompileResult,
    CompiledCase,
    CompiledProfile,
)
from alj_core.cases_profile_compile import compile_profile
from alj_core.cases_profiles import selected_profile_names
from alj_core.cases_schema import validate_case_block, validate_concrete_case
from alj_core.errors import JudgeError
from alj_core.problem import tool_paths


def compile_cases_file(path: Path, profile: str | None = None) -> CaseCompileResult:
    """케이스 파일 소스와 설정을 실행 가능한 산출물과 진단 정보로 변환합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
    """
    path = path.resolve()
    data, diagnostics, lines = load_yaml(path)
    if diagnostics:
        return CaseCompileResult(path=path, diagnostics=diagnostics)
    if not isinstance(data, dict):
        return CaseCompileResult(
            path=path,
            diagnostics=[diagnostic(path, "cases.yml must be a mapping", line=1, location="root")],
        )
    profiles = data.get("profiles")
    names, selection_diagnostics = selected_profile_names(path, lines, profiles, profile)
    if selection_diagnostics:
        return CaseCompileResult(path=path, diagnostics=selection_diagnostics)
    compiled_profiles = []
    all_diagnostics = []
    for name in names:
        compiled_profile, profile_diagnostics = compile_profile(path, lines, name, profiles[name])
        all_diagnostics.extend(profile_diagnostics)
        if compiled_profile is not None:
            compiled_profiles.append(compiled_profile)
    return CaseCompileResult(
        path=path,
        profiles=compiled_profiles,
        diagnostics=all_diagnostics,
    )


def compile_problem_cases(
    problem_id: str,
    profile: str | None = None,
    root: Path | None = None,
) -> CaseCompileResult:
    """문제 케이스 소스와 설정을 실행 가능한 산출물과 진단 정보로 변환합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
    """
    _, _, _, paths = tool_paths(problem_id, root)
    return compile_cases_file(paths["generatorConfig"], profile)


def ensure_cases_compiled(
    problem_id: str,
    profile: str | None = None,
    root: Path | None = None,
) -> CaseCompileResult:
    """케이스 compiled 조건을 확인하고 위반 시 호출자가 중단할 수 있는 예외를 발생시킵니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
    """
    result = compile_problem_cases(problem_id, profile, root)
    if not result.valid:
        raise JudgeError("cases.yml compile failed\n\n" + format_compile_result(result))
    return result


__all__ = [
    "CaseCompileDiagnostic",
    "CaseCompileResult",
    "CompiledCase",
    "CompiledProfile",
    "SAFE_CASE_NAME_RE",
    "VARIABLE_MESSAGE_PREFIX",
    "compile_cases_file",
    "compile_problem_cases",
    "compile_profile",
    "diagnostic",
    "ensure_cases_compiled",
    "expand_profile_cases",
    "expansion_error_location",
    "expression_mentions_variable",
    "find_case_line",
    "find_profile_line",
    "find_variable_reference_location",
    "format_compile_result",
    "format_diagnostic",
    "is_integer",
    "line_indent",
    "load_yaml",
    "location_part",
    "matrix_error_location",
    "profile_bounds",
    "repeat_error_location",
    "result_to_json",
    "selected_profile_names",
    "type_label",
    "validate_case_block",
    "validate_concrete_case",
]
