from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from judge.core.errors import JudgeError
from judge.core.generation import generate
from judge.core.submission import run_submission

ROOT = Path(__file__).resolve().parents[1]


class CasesCompileIntegrationTest(unittest.TestCase):
    """Integration checks for preflight cases.yml compilation."""

    def test_generate_stops_before_tool_compile_when_cases_compile_fails(self) -> None:
        """Generate should not compile generator binaries after cases.yml fails."""
        with (
            patch(
                "judge.core.generation.ensure_cases_compiled",
                side_effect=JudgeError("cases.yml compile failed"),
            ) as ensure,
            patch("judge.core.generation.compile_problem_tools") as compile_tools,
        ):
            with self.assertRaisesRegex(JudgeError, "cases.yml compile failed"):
                generate("06", "sample")

        ensure.assert_called_once_with("06", "sample", None)
        compile_tools.assert_not_called()

    def test_run_stops_before_submission_compile_when_cases_compile_fails(self) -> None:
        """Run should not compile user code after cases.yml fails."""
        source = ROOT / "tests" / "fixtures" / "accepted.py"
        with (
            patch(
                "judge.core.submission.ensure_cases_compiled",
                side_effect=JudgeError("cases.yml compile failed"),
            ) as ensure,
            patch("judge.core.submission.prepare_user_submission") as prepare_submission,
        ):
            with self.assertRaisesRegex(JudgeError, "cases.yml compile failed"):
                run_submission(source, "06", "sample")

        ensure.assert_called_once_with("06", "sample", None)
        prepare_submission.assert_not_called()


if __name__ == "__main__":
    unittest.main()
