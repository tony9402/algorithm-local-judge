"""케이스 프로필 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from judge.core.cases_diagnostics import diagnostic, find_profile_line
from judge.core.cases_models import CaseCompileDiagnostic

FULL_PROFILE = "full"


def selected_profile_names(
    path: Path,
    lines: list[str],
    profiles: Any,
    profile: str | None,
) -> tuple[list[str], list[CaseCompileDiagnostic]]:
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
        if profile == FULL_PROFILE and profile not in profiles:
            return list(profiles), []
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
