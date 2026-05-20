from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from judge.core.errors import JudgeError
from judge.core.solution_validation import (
    discover_solution_expectations,
    expected_status_from_solution_name,
    verify_problem_solutions,
)
from judge.utils.fs import write_json


def create_problem(root: Path) -> Path:
    """Create a minimal problem tree for solution verification unit tests."""
    problem = root / "problems" / "01"
    for path in [
        problem / "generator" / "generator.cpp",
        problem / "generator" / "cases.yml",
        problem / "validator" / "validator.cpp",
        problem / "checker" / "judge.cpp",
        problem / "solutions" / "main_solution.ac.cpp",
        problem / "solutions" / "wrong_solution.wa.py",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// placeholder\n", encoding="utf-8")
    write_json(
        problem / "problem.json",
        {
            "schemaVersion": 1,
            "problemId": "01",
            "title": "unit",
            "version": 1,
            "tools": {
                "generator": "generator/generator.cpp",
                "generatorConfig": "generator/cases.yml",
                "validator": "validator/validator.cpp",
                "checker": "checker/judge.cpp",
                "solution": "solutions/main_solution.ac.cpp",
            },
            "defaultProfile": "hidden",
            "limits": {},
        },
    )
    return problem


class SolutionValidationTest(unittest.TestCase):
    """Tests for expected-result solution checks used before pack builds."""

    def test_expected_status_from_solution_name(self) -> None:
        """Expected result tokens should map to judge statuses."""
        self.assertEqual(
            expected_status_from_solution_name(Path("main_solution.ac.cpp")),
            ("ac", "accepted"),
        )
        self.assertEqual(
            expected_status_from_solution_name(Path("wrong_solution.wa.py")),
            ("wa", "wrong_answer"),
        )
        self.assertEqual(
            expected_status_from_solution_name(Path("slow.tle.java")),
            ("tle", "time_limit"),
        )
        self.assertEqual(
            expected_status_from_solution_name(Path("memory.mle.cpp")),
            ("mle", "memory_limit"),
        )
        with self.assertRaisesRegex(JudgeError, "expected result token"):
            expected_status_from_solution_name(Path("helper.cpp"))

    def test_discover_solution_expectations_requires_tokens(self) -> None:
        """Every supported source under solutions should carry an expectation token."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-test-") as tmp:
            problem = Path(tmp) / "problem"
            solutions = problem / "solutions"
            solutions.mkdir(parents=True)
            (solutions / "main_solution.ac.cpp").write_text("", encoding="utf-8")
            (solutions / "helper.cpp").write_text("", encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "expected result token"):
                discover_solution_expectations(problem)

    def test_verify_problem_solutions_passes_matching_results(self) -> None:
        """Verification should pass when every solution produces its expected status."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-test-") as tmp:
            root = Path(tmp)
            create_problem(root)
            run_root = root / "runs"

            def fake_run_submission(
                source: Path,
                problem_id: str | None = None,
                profile: str | None = None,
                root: Path | None = None,
                stop_on_first_failure: bool = True,
            ) -> Path:
                run_dir = run_root / source.stem
                status = "wrong_answer" if ".wa." in source.name else "accepted"
                write_json(
                    run_dir / "result.json",
                    {
                        "runId": source.stem,
                        "problemId": problem_id,
                        "profile": profile,
                        "language": "python" if source.suffix == ".py" else "cpp",
                        "status": status,
                        "cases": [{"case": "001", "status": "ok"}],
                        "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1},
                    },
                )
                return run_dir

            with (
                patch("judge.core.solution_validation.generate", return_value=root / "cache"),
                patch(
                    "judge.core.solution_validation.run_submission",
                    side_effect=fake_run_submission,
                ),
            ):
                result = verify_problem_solutions("01", "hidden", root)

        self.assertTrue(result.passed)
        self.assertEqual(len(result.checks), 2)

    def test_verify_problem_solutions_reports_mismatch(self) -> None:
        """Verification should fail when hidden data does not catch an expected WA."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-test-") as tmp:
            root = Path(tmp)
            create_problem(root)
            run_root = root / "runs"

            def fake_run_submission(
                source: Path,
                problem_id: str | None = None,
                profile: str | None = None,
                root: Path | None = None,
                stop_on_first_failure: bool = True,
            ) -> Path:
                run_dir = run_root / source.stem
                write_json(
                    run_dir / "result.json",
                    {
                        "runId": source.stem,
                        "problemId": problem_id,
                        "profile": profile,
                        "language": "cpp",
                        "status": "accepted",
                        "cases": [{"case": "001", "status": "ok"}],
                        "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1},
                    },
                )
                return run_dir

            with (
                patch("judge.core.solution_validation.generate", return_value=root / "cache"),
                patch(
                    "judge.core.solution_validation.run_submission",
                    side_effect=fake_run_submission,
                ),
                self.assertRaisesRegex(JudgeError, "expected wrong_answer, got accepted"),
            ):
                verify_problem_solutions("01", "hidden", root)

    def test_verify_problem_solutions_can_return_mismatch_payload(self) -> None:
        """The web UI should receive per-solution mismatch details without reading logs."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-test-") as tmp:
            root = Path(tmp)
            create_problem(root)
            run_root = root / "runs"

            def fake_run_submission(
                source: Path,
                problem_id: str | None = None,
                profile: str | None = None,
                root: Path | None = None,
                stop_on_first_failure: bool = True,
            ) -> Path:
                run_dir = run_root / source.stem
                write_json(
                    run_dir / "result.json",
                    {
                        "runId": source.stem,
                        "problemId": problem_id,
                        "profile": profile,
                        "language": "python" if source.suffix == ".py" else "cpp",
                        "status": "accepted",
                        "cases": [
                            {"case": "001", "status": "ok", "timeMs": 7, "memoryBytes": 2048}
                        ],
                        "metrics": {"maxTimeMs": 7, "maxMemoryBytes": 2048},
                    },
                )
                return run_dir

            with (
                patch("judge.core.solution_validation.generate", return_value=root / "cache"),
                patch(
                    "judge.core.solution_validation.run_submission",
                    side_effect=fake_run_submission,
                ),
            ):
                result = verify_problem_solutions("01", "hidden", root, raise_on_failure=False)

        payload = result.to_dict(root)
        failed = [check for check in payload["checks"] if not check["passed"]]
        self.assertFalse(payload["passed"])
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["source"], "problems/01/solutions/wrong_solution.wa.py")
        self.assertEqual(failed[0]["expectedStatus"], "wrong_answer")
        self.assertEqual(failed[0]["actualStatus"], "accepted")
        self.assertEqual(failed[0]["runId"], "wrong_solution.wa")
        self.assertIn("runs/wrong_solution.wa", failed[0]["message"])
        self.assertEqual(failed[0]["cases"][0]["case"], "001")
        self.assertEqual(failed[0]["metrics"]["maxTimeMs"], 7)
        self.assertEqual(failed[0]["metrics"]["maxMemoryBytes"], 2048)

    def test_verify_problem_solutions_can_limit_to_one_solution(self) -> None:
        """Individual solution tests should not run every discovered solution."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-test-") as tmp:
            root = Path(tmp)
            create_problem(root)
            run_root = root / "runs"

            def fake_run_submission(
                source: Path,
                problem_id: str | None = None,
                profile: str | None = None,
                root: Path | None = None,
                stop_on_first_failure: bool = True,
            ) -> Path:
                run_dir = run_root / source.stem
                write_json(
                    run_dir / "result.json",
                    {
                        "runId": source.stem,
                        "problemId": problem_id,
                        "profile": profile,
                        "language": "python" if source.suffix == ".py" else "cpp",
                        "status": "wrong_answer",
                        "cases": [{"case": "001", "status": "wrong_answer"}],
                        "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1},
                    },
                )
                return run_dir

            with (
                patch("judge.core.solution_validation.generate", return_value=root / "cache"),
                patch(
                    "judge.core.solution_validation.run_submission",
                    side_effect=fake_run_submission,
                ) as mocked_run,
            ):
                result = verify_problem_solutions(
                    "01",
                    "hidden",
                    root,
                    raise_on_failure=False,
                    solution_paths=["solutions/wrong_solution.wa.py"],
                )

        payload = result.to_dict(root)
        self.assertTrue(result.passed)
        self.assertEqual(payload["verifiedCount"], 1)
        self.assertEqual(payload["totalCount"], 1)
        self.assertEqual(payload["skippedCount"], 0)
        self.assertEqual(len(result.checks), 1)
        self.assertEqual(result.checks[0].source.name, "wrong_solution.wa.py")
        self.assertEqual(mocked_run.call_count, 1)
        self.assertFalse(mocked_run.call_args.kwargs["stop_on_first_failure"])


if __name__ == "__main__":
    unittest.main()
