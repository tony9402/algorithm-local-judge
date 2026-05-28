"""솔루션 models 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge.core.paths import rel


@dataclass(frozen=True)
class SolutionExpectation:
    """솔루션 기대 상태 상태와 관련 동작을 하나의 객체로 표현합니다.
    """

    path: Path
    token: str
    status: str


@dataclass(frozen=True)
class SolutionCheckResult:
    """솔루션 검사 결과에 필요한 필드를 한데 묶어 전달하는 데이터 모델입니다.
    """

    source: Path
    expected_status: str
    actual_status: str
    run_id: str | None
    passed: bool
    message: str = ""
    cases: list[dict[str, Any]] | None = None
    metrics: dict[str, Any] | None = None

    def to_dict(self, root: Path | None = None) -> dict[str, object]:
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
    """솔루션 verification 결과에 필요한 필드를 한데 묶어 전달하는 데이터 모델입니다.
    """

    problem_id: str
    profile: str
    checks: list[SolutionCheckResult]
    total_count: int | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self, root: Path | None = None) -> dict[str, object]:
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
