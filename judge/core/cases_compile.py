"""cases_compile 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path

from judge.core.cases_diagnostics import (
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
from judge.core.cases_expansion import expand_profile_cases
from judge.core.cases_format import format_compile_result, format_diagnostic, result_to_json
from judge.core.cases_io import load_yaml
from judge.core.cases_models import (
    CaseCompileDiagnostic,
    CaseCompileResult,
    CompiledCase,
    CompiledProfile,
)
from judge.core.cases_profile_compile import compile_profile
from judge.core.cases_profiles import selected_profile_names
from judge.core.cases_schema import validate_case_block, validate_concrete_case
from judge.core.errors import JudgeError
from judge.core.problem import tool_paths


def compile_cases_file(path: Path, profile: str | None = None) -> CaseCompileResult:
    """compile_cases_file 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
        profile (str | None): `profile` 값입니다.
    
    Returns:
        CaseCompileResult: 처리 결과를 반환합니다.
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
    """compile_problem_cases 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        CaseCompileResult: 처리 결과를 반환합니다.
    """
    _, _, _, paths = tool_paths(problem_id, root)
    return compile_cases_file(paths["generatorConfig"], profile)


def ensure_cases_compiled(
    problem_id: str,
    profile: str | None = None,
    root: Path | None = None,
) -> CaseCompileResult:
    """ensure_cases_compiled 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        CaseCompileResult: 처리 결과를 반환합니다.
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
