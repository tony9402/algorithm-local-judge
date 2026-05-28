"""solution_models 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge.core.paths import rel


@dataclass(frozen=True)
class SolutionExpectation:
    """SolutionExpectation 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    path: Path
    token: str
    status: str


@dataclass(frozen=True)
class SolutionCheckResult:
    """SolutionCheckResult 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
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
        """to_dict 함수를 실행하고 결과를 반환합니다.
        
        Args:
            self (Any): 현재 인스턴스를 나타내는 객체입니다.
            root (Path | None): `root` 값입니다.
        
        Returns:
            dict[str, object]: 처리 결과를 반환합니다.
        """
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
    """SolutionVerificationResult 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    problem_id: str
    profile: str
    checks: list[SolutionCheckResult]
    total_count: int | None = None

    @property
    def passed(self) -> bool:
        """passed 함수를 실행하고 결과를 반환합니다.
        
        Args:
            self (Any): 현재 인스턴스를 나타내는 객체입니다.
        
        Returns:
            bool: 처리 결과를 반환합니다.
        """
        return all(check.passed for check in self.checks)

    def to_dict(self, root: Path | None = None) -> dict[str, object]:
        """to_dict 함수를 실행하고 결과를 반환합니다.
        
        Args:
            self (Any): 현재 인스턴스를 나타내는 객체입니다.
            root (Path | None): `root` 값입니다.
        
        Returns:
            dict[str, object]: 처리 결과를 반환합니다.
        """
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
