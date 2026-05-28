from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge.core.paths import rel


@dataclass(frozen=True)
class SolutionExpectation:
    """One solution source file and the status it is expected to produce."""

    path: Path
    token: str
    status: str


@dataclass(frozen=True)
class SolutionCheckResult:
    """Observed result for one expected solution run."""

    source: Path
    expected_status: str
    actual_status: str
    run_id: str | None
    passed: bool
    message: str = ""
    cases: list[dict[str, Any]] | None = None
    metrics: dict[str, Any] | None = None

    def to_dict(self, root: Path | None = None) -> dict[str, object]:
        """Return a compact serializable representation for CLI/reporting."""
        return {
            "source": rel(self.source, root),
            "expectedStatus": self.expected_status,
            "actualStatus": self.actual_status,
            "runId": self.run_id,
            "passed": self.passed,
            "message": self.message,
            "cases": self.cases or [],
            "metrics": self.metrics or {},
        }


@dataclass(frozen=True)
class SolutionVerificationResult:
    """Aggregate result for solution expectation verification."""

    problem_id: str
    profile: str
    checks: list[SolutionCheckResult]
    total_count: int | None = None

    @property
    def passed(self) -> bool:
        """Return whether every discovered solution matched its expected status."""
        return all(check.passed for check in self.checks)

    def to_dict(self, root: Path | None = None) -> dict[str, object]:
        """Return a compact serializable representation for pack build output."""
        total = self.total_count if self.total_count is not None else len(self.checks)
        return {
            "problemId": self.problem_id,
            "profile": self.profile,
            "passed": self.passed,
            "verifiedCount": len(self.checks),
            "totalCount": total,
            "skippedCount": max(0, total - len(self.checks)),
            "checks": [check.to_dict(root) for check in self.checks],
        }
