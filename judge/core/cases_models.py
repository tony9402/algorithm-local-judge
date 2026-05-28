from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
