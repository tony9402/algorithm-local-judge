from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from commons.generate import expand_cases
from judge.core.errors import JudgeError
from judge.core.paths import rel
from judge.core.problem import tool_paths

SAFE_CASE_NAME_RE = r"^[A-Za-z0-9_.-]+$"
VARIABLE_MESSAGE_PREFIX = "unknown variable: "


@dataclass(frozen=True)
class CaseCompileDiagnostic:
    """One cases.yml compile diagnostic."""

    severity: str
    path: str
    line: int | None
    profile: str | None
    location: str
    message: str
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable diagnostic."""
        return {
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "profile": self.profile,
            "location": self.location,
            "message": self.message,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class CompiledCase:
    """One expanded case definition summary."""

    index: int
    name: str
    type: str
    seed: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable case summary."""
        return {
            "index": self.index,
            "name": self.name,
            "type": self.type,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class CompiledProfile:
    """Expanded case definitions for one profile."""

    name: str
    cases: list[CompiledCase] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable profile summary."""
        return {
            "name": self.name,
            "caseCount": len(self.cases),
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class CaseCompileResult:
    """Result of compiling a cases.yml file."""

    path: Path
    profiles: list[CompiledProfile] = field(default_factory=list)
    diagnostics: list[CaseCompileDiagnostic] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Return whether the compile produced no error diagnostics."""
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable compile result."""
        return {
            "valid": self.valid,
            "path": str(self.path),
            "profiles": [profile.to_dict() for profile in self.profiles],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def diagnostic(
    path: Path,
    message: str,
    *,
    line: int | None = None,
    profile: str | None = None,
    location: str = "",
    hint: str | None = None,
) -> CaseCompileDiagnostic:
    """Create an error diagnostic for one file location."""
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
    """Return a user-facing type label for YAML values."""
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def is_integer(value: Any) -> bool:
    """Return whether a YAML value is an integer but not a boolean."""
    return isinstance(value, int) and not isinstance(value, bool)


def line_indent(line: str) -> int:
    """Return the leading-space indentation for one line."""
    return len(line) - len(line.lstrip(" "))


def find_profile_line(lines: list[str], profile: str) -> int | None:
    """Find the 1-based line for a profile key when possible."""
    target = f"{profile}:"
    for index, line in enumerate(lines, start=1):
        if line_indent(line) == 2 and line.strip() == target:
            return index
    return None


def profile_bounds(lines: list[str], profile: str) -> tuple[int, int] | None:
    """Return zero-based line bounds for one profile block."""
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
    """Find the 1-based line for a top-level case entry."""
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


def load_yaml(path: Path) -> tuple[Any | None, list[CaseCompileDiagnostic], list[str]]:
    """Load YAML and return data plus parse diagnostics."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [diagnostic(path, str(exc), location="file")], []
    lines = text.splitlines()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        return None, [diagnostic(path, str(exc), line=line, location="yaml")], lines
    return data, [], lines


def selected_profile_names(
    path: Path,
    lines: list[str],
    profiles: Any,
    profile: str | None,
) -> tuple[list[str], list[CaseCompileDiagnostic]]:
    """Return profile names to compile, or diagnostics if selection is invalid."""
    if not isinstance(profiles, dict):
        return [], [diagnostic(path, "`profiles` must be a mapping", location="profiles")]
    if not profiles:
        return [], [
            diagnostic(
                path,
                "`profiles` must define at least one profile",
                location="profiles",
            )
        ]
    if profile is not None:
        if profile not in profiles:
            return [], [
                diagnostic(
                    path,
                    f"unknown profile: {profile}",
                    line=find_profile_line(lines, profile),
                    profile=profile,
                    location=f"profiles.{profile}",
                )
            ]
        return [profile], []
    return list(profiles), []


def location_part(key: str | int) -> str:
    """Return a dotted diagnostic location segment."""
    if isinstance(key, int):
        return f"[{key}]"
    if re.fullmatch(SAFE_CASE_NAME_RE, key):
        return f".{key}"
    return f"[{key!r}]"


def expression_mentions_variable(value: str, variable: str) -> bool:
    """Return whether a template expression string appears to reference a variable."""
    return "${" in value and re.search(rf"\b{re.escape(variable)}\b", value) is not None


def find_variable_reference_location(value: Any, variable: str) -> str | None:
    """Find the first nested field that appears to reference a variable."""
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
    """Return the most specific location available for a DSL expansion error."""
    if not isinstance(case, dict):
        return base_location
    if "matrix" in case:
        return matrix_error_location(case["matrix"], base_location, message)
    if "repeat" in case:
        return repeat_error_location(case["repeat"], base_location, message)
    return base_location


def matrix_error_location(block: Any, base_location: str, message: str) -> str:
    """Return a diagnostic location for a matrix expansion error."""
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
    """Return a diagnostic location for a repeat expansion error."""
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


def validate_case_block(
    path: Path,
    lines: list[str],
    profile: str,
    case: Any,
    case_index: int,
) -> list[CaseCompileDiagnostic]:
    """Validate a top-level case DSL block before expansion."""
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


def validate_concrete_case(
    path: Path,
    profile: str,
    case: Any,
    index: int,
    seen_names: set[str],
) -> tuple[CompiledCase | None, list[CaseCompileDiagnostic]]:
    """Validate one expanded case and return its summary."""
    location = f"expanded[{index - 1}]"
    if not isinstance(case, dict):
        return None, [
            diagnostic(
                path,
                f"expanded case must be a mapping, got {type_label(case)}",
                profile=profile,
                location=location,
            )
        ]
    name = case.get("name")
    case_type = case.get("type")
    diagnostics = []
    if not isinstance(name, str) or not name:
        diagnostics.append(
            diagnostic(path, "case name is required", profile=profile, location=f"{location}.name")
        )
    elif name in seen_names:
        diagnostics.append(
            diagnostic(
                path,
                f"duplicate case name: {name}",
                profile=profile,
                location=f"{location}.name",
            )
        )
    elif re.fullmatch(SAFE_CASE_NAME_RE, name) is None:
        diagnostics.append(
            diagnostic(
                path,
                f"unsafe case name: {name}",
                profile=profile,
                location=f"{location}.name",
                hint="Use only letters, digits, underscore, dash, and dot in case names.",
            )
        )
    else:
        seen_names.add(name)
    if case_type is None:
        diagnostics.append(
            diagnostic(
                path,
                "case type is required",
                profile=profile,
                location=f"{location}.type",
            )
        )
    elif case_type not in {"fixed", "generator", "template"}:
        diagnostics.append(
            diagnostic(
                path,
                f"unknown case type: {case_type}",
                profile=profile,
                location=f"{location}.type",
            )
        )
    if case_type == "fixed":
        if "content" not in case:
            diagnostics.append(
                diagnostic(
                    path,
                    "fixed case requires content",
                    profile=profile,
                    location=f"{location}.content",
                )
            )
        elif not isinstance(case["content"], str):
            diagnostics.append(
                diagnostic(
                    path,
                    "fixed case content must be a string",
                    profile=profile,
                    location=f"{location}.content",
                )
            )
    if case_type == "generator":
        seed = case.get("seed")
        if not is_integer(seed):
            diagnostics.append(
                diagnostic(
                    path,
                    "generator case requires integer seed",
                    profile=profile,
                    location=f"{location}.seed",
                )
            )
        if "args" in case and not isinstance(case["args"], dict):
            diagnostics.append(
                diagnostic(
                    path,
                    "generator args must be a mapping",
                    profile=profile,
                    location=f"{location}.args",
                )
            )
    if case_type == "template":
        template = case.get("template")
        if "template" not in case:
            diagnostics.append(
                diagnostic(
                    path,
                    "template case requires template",
                    profile=profile,
                    location=f"{location}.template",
                )
            )
        elif not isinstance(template, str):
            diagnostics.append(
                diagnostic(
                    path,
                    "template case template must be a string",
                    profile=profile,
                    location=f"{location}.template",
                )
            )
        if "vars" in case and not isinstance(case["vars"], dict):
            diagnostics.append(
                diagnostic(
                    path,
                    "template vars must be a mapping",
                    profile=profile,
                    location=f"{location}.vars",
                )
            )
    if diagnostics:
        return None, diagnostics
    return CompiledCase(index=index, name=name, type=case_type, seed=case.get("seed")), []


def expand_profile_cases(
    path: Path,
    lines: list[str],
    profile: str,
    cases: list[Any],
) -> tuple[list[dict[str, Any]], list[CaseCompileDiagnostic]]:
    """Expand top-level case blocks and keep errors tied to the failing block."""
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


def compile_profile(
    path: Path,
    lines: list[str],
    profile: str,
    profile_config: Any,
) -> tuple[CompiledProfile | None, list[CaseCompileDiagnostic]]:
    """Compile one profile from raw YAML data."""
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


def format_diagnostic(diagnostic_item: CaseCompileDiagnostic) -> str:
    """Format one diagnostic for terminal output."""
    location = diagnostic_item.location or "cases.yml"
    if diagnostic_item.profile:
        location = f"profile {diagnostic_item.profile}, {location}"
    line = f":{diagnostic_item.line}" if diagnostic_item.line is not None else ""
    lines = [f"{diagnostic_item.path}{line}", f"  {location}", f"  {diagnostic_item.message}"]
    if diagnostic_item.hint:
        lines.extend(["", "hint:", f"  {diagnostic_item.hint}"])
    return "\n".join(lines)


def format_compile_result(
    result: CaseCompileResult,
    expanded: bool = False,
    max_preview: int | None = None,
) -> str:
    """Format a compile result for terminal output."""
    if not result.valid:
        body = "\n\n".join(format_diagnostic(item) for item in result.diagnostics)
        return "cases.yml: invalid\n\n" + body
    lines = ["cases.yml: ok"]
    for profile in result.profiles:
        lines.append(f"profile {profile.name}: {len(profile.cases)} case(s)")
        if expanded:
            preview_cases = profile.cases[:max_preview]
            for case in preview_cases:
                seed = f" seed={case.seed}" if case.seed is not None else ""
                lines.append(f"  {case.index:03d} {case.name} {case.type}{seed}")
            hidden_count = len(profile.cases) - len(preview_cases)
            if hidden_count > 0:
                lines.append(f"  ... {hidden_count} more case(s)")
    return "\n".join(lines)


def result_to_json(result: CaseCompileResult) -> str:
    """Serialize a compile result as pretty JSON."""
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
