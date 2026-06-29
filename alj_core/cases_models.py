"""케이스 models 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CaseCompileDiagnostic:
    """케이스 컴파일 진단 정보 상태와 관련 동작을 하나의 객체로 표현합니다.
    """

    severity: str
    path: str
    line: int | None
    profile: str | None
    location: str
    message: str
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
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
    """compiled 케이스에 필요한 필드를 한데 묶어 전달하는 데이터 모델입니다.
    """

    index: int
    name: str
    type: str
    seed: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "type": self.type,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class CompiledProfile:
    """compiled 프로필에 필요한 필드를 한데 묶어 전달하는 데이터 모델입니다.
    """

    name: str
    cases: list[CompiledCase] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "caseCount": len(self.cases),
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class CaseCompileResult:
    """케이스 컴파일 결과에 필요한 필드를 한데 묶어 전달하는 데이터 모델입니다.
    """

    path: Path
    profiles: list[CompiledProfile] = field(default_factory=list)
    diagnostics: list[CaseCompileDiagnostic] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "path": str(self.path),
            "profiles": [profile.to_dict() for profile in self.profiles],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }
