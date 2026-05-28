"""케이스 io 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from judge.core.cases_diagnostics import diagnostic
from judge.core.cases_models import CaseCompileDiagnostic


def load_yaml(path: Path) -> tuple[Any | None, list[CaseCompileDiagnostic], list[str]]:
    """yaml 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.

    Returns:
        tuple[Any | None, list[CaseCompileDiagnostic], list[str]]: 호출자가 순회하거나 화면에 표시할 yaml 항목 목록입니다.
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
