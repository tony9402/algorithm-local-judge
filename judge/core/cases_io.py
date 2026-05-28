"""cases_io 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from judge.core.cases_diagnostics import diagnostic
from judge.core.cases_models import CaseCompileDiagnostic


def load_yaml(path: Path) -> tuple[Any | None, list[CaseCompileDiagnostic], list[str]]:
    """load_yaml 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
    
    Returns:
        tuple[Any | None, list[CaseCompileDiagnostic], list[str]]: 처리 결과를 반환합니다.
    """
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
