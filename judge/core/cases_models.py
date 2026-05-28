"""cases_models 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CaseCompileDiagnostic:
    """CaseCompileDiagnostic 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    severity: str
    path: str
    line: int | None
    profile: str | None
    location: str
    message: str
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """to_dict 함수를 실행하고 결과를 반환합니다.
        
        Args:
            self (Any): 현재 인스턴스를 나타내는 객체입니다.
        
        Returns:
            dict[str, Any]: 처리 결과를 반환합니다.
        """
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
    """CompiledCase 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    index: int
    name: str
    type: str
    seed: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """to_dict 함수를 실행하고 결과를 반환합니다.
        
        Args:
            self (Any): 현재 인스턴스를 나타내는 객체입니다.
        
        Returns:
            dict[str, Any]: 처리 결과를 반환합니다.
        """
        return {
            "index": self.index,
            "name": self.name,
            "type": self.type,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class CompiledProfile:
    """CompiledProfile 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    name: str
    cases: list[CompiledCase] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """to_dict 함수를 실행하고 결과를 반환합니다.
        
        Args:
            self (Any): 현재 인스턴스를 나타내는 객체입니다.
        
        Returns:
            dict[str, Any]: 처리 결과를 반환합니다.
        """
        return {
            "name": self.name,
            "caseCount": len(self.cases),
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class CaseCompileResult:
    """CaseCompileResult 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    path: Path
    profiles: list[CompiledProfile] = field(default_factory=list)
    diagnostics: list[CaseCompileDiagnostic] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """valid 함수를 실행하고 결과를 반환합니다.
        
        Args:
            self (Any): 현재 인스턴스를 나타내는 객체입니다.
        
        Returns:
            bool: 처리 결과를 반환합니다.
        """
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)

    def to_dict(self) -> dict[str, Any]:
        """to_dict 함수를 실행하고 결과를 반환합니다.
        
        Args:
            self (Any): 현재 인스턴스를 나타내는 객체입니다.
        
        Returns:
            dict[str, Any]: 처리 결과를 반환합니다.
        """
        return {
            "valid": self.valid,
            "path": str(self.path),
            "profiles": [profile.to_dict() for profile in self.profiles],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }
