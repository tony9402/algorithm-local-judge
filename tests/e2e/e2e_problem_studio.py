"""문제 스튜디오 브라우저 종단 간 테스트 패키지를 pytest가 수집할 수 있게 연결하는 모듈입니다."""

from __future__ import annotations

from tests.e2e.problem_studio_authoring_tests import ProblemStudioAuthoringE2ETest
from tests.e2e.problem_studio_build_tests import ProblemStudioBuildE2ETest
from tests.e2e.problem_studio_git_tests import ProblemStudioGitE2ETest
from tests.e2e.problem_studio_solution_tests import ProblemStudioSolutionE2ETest

__all__ = [
    "ProblemStudioAuthoringE2ETest",
    "ProblemStudioBuildE2ETest",
    "ProblemStudioGitE2ETest",
    "ProblemStudioSolutionE2ETest",
]
