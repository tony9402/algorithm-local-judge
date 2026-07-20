"""케이스 형식 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

import json

from alj_core.cases_models import CaseCompileDiagnostic, CaseCompileResult


def format_diagnostic(diagnostic_item: CaseCompileDiagnostic) -> str:
    """진단 정보 데이터를 CLI나 UI에 표시할 문자열로 변환합니다.

    Args:
        diagnostic_item (CaseCompileDiagnostic): 진단 정보을 계산하거나 검증할 때 필요한 진단 정보 item 입력입니다.

    Returns:
        str: 콘솔, 로그, 또는 이벤트 스트림에 바로 쓸 수 있는 문자열입니다.
    """
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
    """컴파일 결과 데이터를 CLI나 UI에 표시할 문자열로 변환합니다.

    Args:
        result (CaseCompileResult): 컴파일 결과을 계산하거나 검증할 때 필요한 결과 입력입니다.
        expanded (bool): 컴파일 결과 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        max_preview (int | None): 컴파일 결과을 계산하거나 검증할 때 필요한 max 미리보기 입력입니다.

    Returns:
        str: 콘솔, 로그, 또는 이벤트 스트림에 바로 쓸 수 있는 문자열입니다.
    """
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
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
