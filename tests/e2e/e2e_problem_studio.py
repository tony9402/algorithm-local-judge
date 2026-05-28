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
