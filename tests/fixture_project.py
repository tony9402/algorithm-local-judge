"""저장소 외부 문제 팩에 의존하지 않는 테스트 프로젝트를 준비합니다."""

from __future__ import annotations

import shutil
from pathlib import Path

FIXTURE_PROBLEMS_ROOT = (
    Path(__file__).resolve().parent / "fixtures" / "problem-package" / "problems"
)


def copy_problem_fixture(project_root: Path, problem_id: str = "06") -> Path:
    """내부 문제 fixture를 격리된 프로젝트로 복사하고 프로젝트 루트를 반환합니다."""
    shutil.copytree(
        FIXTURE_PROBLEMS_ROOT / problem_id,
        project_root / "problems" / problem_id,
    )
    return project_root
