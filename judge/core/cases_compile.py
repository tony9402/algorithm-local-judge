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
    """Compile a cases.yml file into expanded case summaries and diagnostics."""
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
    """Compile the generator cases.yml file for one problem."""
    _, _, _, paths = tool_paths(problem_id, root)
    return compile_cases_file(paths["generatorConfig"], profile)


def ensure_cases_compiled(
    problem_id: str,
    profile: str | None = None,
    root: Path | None = None,
) -> CaseCompileResult:
    """Compile cases.yml and raise a JudgeError if diagnostics contain errors."""
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
