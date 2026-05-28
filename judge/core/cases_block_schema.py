"""케이스 block 스키마 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from judge.core.cases_diagnostics import (
    diagnostic,
    find_case_line,
    type_label,
)
from judge.core.cases_models import CaseCompileDiagnostic


def validate_case_block(
    path: Path,
    lines: list[str],
    profile: str,
    case: Any,
    case_index: int,
) -> list[CaseCompileDiagnostic]:
    """케이스 block 값이 허용되는 형식과 정책을 만족하는지 검사합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
        lines (list[str]): 케이스 block을 계산하거나 검증할 때 필요한 lines 입력입니다.
        profile (str): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        case (Any): 케이스 block 목록을 순회할 때 현재 처리 중인 항목입니다.
        case_index (int): 현재 처리 중인 케이스의 1부터 시작하는 순번입니다.

    Returns:
        list[CaseCompileDiagnostic]: 호출자가 순회하거나 화면에 표시할 케이스 block 항목 목록입니다.
    """
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
