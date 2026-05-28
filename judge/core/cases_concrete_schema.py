"""케이스 concrete 스키마 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from judge.core.cases_diagnostics import (
    SAFE_CASE_NAME_RE,
    diagnostic,
    is_integer,
    type_label,
)
from judge.core.cases_models import CaseCompileDiagnostic, CompiledCase


def validate_concrete_case(
    path: Path,
    profile: str,
    case: Any,
    index: int,
    seen_names: set[str],
) -> tuple[CompiledCase | None, list[CaseCompileDiagnostic]]:
    """concrete 케이스 값이 허용되는 형식과 정책을 만족하는지 검사합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
        profile (str): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        case (Any): concrete 케이스 목록을 순회할 때 현재 처리 중인 항목입니다.
        index (int): concrete 케이스을 계산하거나 검증할 때 필요한 index 입력입니다.
        seen_names (set[str]): concrete 케이스을 계산하거나 검증할 때 필요한 seen names 입력입니다.

    Returns:
        tuple[CompiledCase | None, list[CaseCompileDiagnostic]]: 호출자가 순회하거나 화면에 표시할 concrete 케이스 항목 목록입니다.
    """
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
    _validate_fixed_case(path, profile, case, case_type, location, diagnostics)
    _validate_generator_case(path, profile, case, case_type, location, diagnostics)
    _validate_template_case(path, profile, case, case_type, location, diagnostics)
    if diagnostics:
        return None, diagnostics
    return CompiledCase(index=index, name=name, type=case_type, seed=case.get("seed")), []


def _validate_fixed_case(
    path: Path,
    profile: str,
    case: dict[str, Any],
    case_type: Any,
    location: str,
    diagnostics: list[CaseCompileDiagnostic],
) -> None:
    if case_type != "fixed":
        return
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


def _validate_generator_case(
    path: Path,
    profile: str,
    case: dict[str, Any],
    case_type: Any,
    location: str,
    diagnostics: list[CaseCompileDiagnostic],
) -> None:
    if case_type != "generator":
        return
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


def _validate_template_case(
    path: Path,
    profile: str,
    case: dict[str, Any],
    case_type: Any,
    location: str,
    diagnostics: list[CaseCompileDiagnostic],
) -> None:
    if case_type != "template":
        return
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
