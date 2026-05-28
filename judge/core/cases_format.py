from __future__ import annotations

import json

from judge.core.cases_models import CaseCompileDiagnostic, CaseCompileResult


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
