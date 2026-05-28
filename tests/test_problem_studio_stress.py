from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from commons.job_queue import CancelToken, JobCancelledError
from judge.core.errors import JudgeError
from judge.utils.fs import write_json
from problem_studio.core.stress import append_stress_case, stress_test_solutions


def write_executable(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def create_stress_problem(root: Path) -> tuple[Path, dict[str, Path]]:
    problem = root / "problems" / "alpha"
    for path in [
        problem / "generator" / "generator.cpp",
        problem / "validator" / "validator.cpp",
        problem / "checker" / "judge.cpp",
        problem / "solutions" / "main_solution.ac.cpp",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// placeholder\n", encoding="utf-8")
    (problem / "generator" / "cases.yml").write_text(
        """profiles:
  hidden:
    cases:
      - name: hidden-seed
        type: generator
        seed: 1
        args:
          n: 7
""",
        encoding="utf-8",
    )
    (problem / "solutions" / "copy.ac.py").write_text(
        "import sys\nsys.stdout.write(sys.stdin.read())\n",
        encoding="utf-8",
    )
    (problem / "solutions" / "sneaky.wa.py").write_text(
        "import sys\nsys.stdout.write(sys.stdin.read())\n",
        encoding="utf-8",
    )
    (problem / "solutions" / "broken.ac.py").write_text(
        "print(0)\n",
        encoding="utf-8",
    )
    write_json(
        problem / "problem.json",
        {
            "schemaVersion": 1,
            "problemId": "alpha",
            "title": "stress",
            "version": 1,
            "tools": {
                "generator": "generator/generator.cpp",
                "generatorConfig": "generator/cases.yml",
                "validator": "validator/validator.cpp",
                "checker": "checker/judge.cpp",
                "solution": "solutions/main_solution.ac.cpp",
            },
            "defaultProfile": "hidden",
            "limits": {
                "compileTimeoutMs": 5000,
                "generationTimeoutMs": 5000,
                "solutionTimeoutMs": 2000,
                "userTimeoutMs": 2000,
            },
        },
    )
    tools_dir = root / "tools"
    tools = {
        "generator": write_executable(
            tools_dir / "generator.py",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "seed = int(sys.argv[1])\n"
            "print(seed % 1000000 + 1)\n",
        ),
        "validator": write_executable(
            tools_dir / "validator.py",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.stdin.read()\n",
        ),
        "checker": write_executable(
            tools_dir / "checker.py",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "actual = open(sys.argv[2], encoding='utf-8').read().strip()\n"
            "expected = open(sys.argv[3], encoding='utf-8').read().strip()\n"
            "raise SystemExit(0 if actual == expected else 1)\n",
        ),
        "solution": write_executable(
            tools_dir / "solution.py",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.stdout.write(sys.stdin.read())\n",
        ),
    }
    return problem, tools


class CyclingRng:
    def __init__(self, values: list[int]) -> None:
        self.values = list(values)

    def randrange(self, _start: int, _stop: int) -> int:
        return self.values.pop(0)

    def choice(self, values):
        return values[0]


class ProblemStudioStressTest(unittest.TestCase):
    def run_with_tools(self, root: Path, tools: dict[str, Path], **kwargs):
        with patch("problem_studio.core.stress.compile_problem_tools", return_value=tools):
            return stress_test_solutions(root, "alpha", "hidden", **kwargs)

    def test_toy_problem_stress_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-stress-test-") as tmp:
            root = Path(tmp)
            _problem, tools = create_stress_problem(root)

            result = self.run_with_tools(
                root,
                tools,
                max_cases=2,
                solutions=["solutions/copy.ac.py"],
                rng=CyclingRng([101, 202]),
            )

        self.assertTrue(result["passed"])
        self.assertEqual(result["iterations"], 2)
        self.assertEqual(result["mismatchCount"], 0)

    def test_non_ac_expectation_allows_accepted_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-stress-test-") as tmp:
            root = Path(tmp)
            _problem, tools = create_stress_problem(root)

            result = self.run_with_tools(
                root,
                tools,
                max_cases=1,
                solutions=["solutions/sneaky.wa.py"],
                rng=CyclingRng([303]),
            )

        self.assertTrue(result["passed"])
        self.assertEqual(result["iterations"], 1)
        self.assertEqual(result["mismatchCount"], 0)
        self.assertEqual(result["mismatches"], [])

    def test_ac_expected_wrong_solution_creates_mismatch_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-stress-test-") as tmp:
            root = Path(tmp)
            _problem, tools = create_stress_problem(root)

            result = self.run_with_tools(
                root,
                tools,
                max_cases=1,
                solutions=["solutions/broken.ac.py"],
                rng=CyclingRng([303]),
            )

            mismatch = result["mismatches"][0]
            self.assertFalse(result["passed"])
            self.assertEqual(mismatch["expectedStatus"], "accepted")
            self.assertEqual(mismatch["actualStatus"], "wrong_answer")
            self.assertEqual(mismatch["seed"], 303)
            self.assertEqual(mismatch["args"], {"n": 7})
            self.assertEqual(mismatch["generatorCaseName"], "hidden-seed")
            self.assertIn("inputHash", mismatch)
            self.assertTrue(
                (root / ".judge-cache" / "stress" / result["stressRunId"] / "mismatches").exists()
            )

    def test_seed_is_random_source_driven_and_unique_within_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-stress-test-") as tmp:
            root = Path(tmp)
            _problem, tools = create_stress_problem(root)

            result = self.run_with_tools(
                root,
                tools,
                max_cases=3,
                stop_on_first_mismatch=False,
                solutions=["solutions/broken.ac.py"],
                rng=CyclingRng([100, 100, 500, 900]),
            )

        seeds = [item["seed"] for item in result["mismatches"]]
        self.assertEqual(seeds, [100, 500, 900])
        self.assertNotEqual(seeds, [1, 2, 3])
        self.assertEqual(len(seeds), len(set(seeds)))

    def test_duration_is_clamped_to_five_minutes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-stress-test-") as tmp:
            root = Path(tmp)
            _problem, tools = create_stress_problem(root)

            result = self.run_with_tools(
                root,
                tools,
                duration_seconds=999,
                max_cases=1,
                solutions=["solutions/copy.ac.py"],
                rng=CyclingRng([404]),
            )

        self.assertEqual(result["durationSeconds"], 300)

    def test_stop_on_first_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-stress-test-") as tmp:
            root = Path(tmp)
            _problem, tools = create_stress_problem(root)

            result = self.run_with_tools(
                root,
                tools,
                max_cases=5,
                stop_on_first_mismatch=True,
                solutions=["solutions/broken.ac.py"],
                rng=CyclingRng([11, 22, 33, 44, 55]),
            )

        self.assertEqual(result["iterations"], 1)
        self.assertEqual(result["mismatchCount"], 1)

    def test_cancel_token_is_checked_before_work(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-stress-test-") as tmp:
            root = Path(tmp)
            _problem, tools = create_stress_problem(root)
            token = CancelToken()
            token.cancel()

            with self.assertRaises(JobCancelledError):
                self.run_with_tools(
                    root,
                    tools,
                    max_cases=1,
                    solutions=["solutions/copy.ac.py"],
                    cancel_token=token,
                    rng=CyclingRng([1]),
                )

    def test_append_fixed_case_validates_cases_and_rejects_duplicate_hash(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-stress-test-") as tmp:
            root = Path(tmp)
            _problem, tools = create_stress_problem(root)
            result = self.run_with_tools(
                root,
                tools,
                max_cases=1,
                solutions=["solutions/broken.ac.py"],
                rng=CyclingRng([515]),
            )
            mismatch = result["mismatches"][0]

            with patch("problem_studio.core.stress.compile_problem_tools", return_value=tools):
                appended = append_stress_case(
                    root,
                    "alpha",
                    "hidden",
                    result["stressRunId"],
                    mismatch["caseId"],
                    mismatch["solutionKey"],
                    mode="fixed",
                    name="stress-fixed-515",
                )
                with self.assertRaisesRegex(JudgeError, "duplicate input hash"):
                    append_stress_case(
                        root,
                        "alpha",
                        "hidden",
                        result["stressRunId"],
                        mismatch["caseId"],
                        mismatch["solutionKey"],
                        mode="fixed",
                        name="stress-fixed-515-copy",
                    )

        self.assertEqual(appended["caseName"], "stress-fixed-515")
        self.assertTrue(appended["compile"]["valid"])

    def test_append_generator_reproduction_case_validates_cases(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-stress-test-") as tmp:
            root = Path(tmp)
            _problem, tools = create_stress_problem(root)
            result = self.run_with_tools(
                root,
                tools,
                max_cases=1,
                solutions=["solutions/broken.ac.py"],
                rng=CyclingRng([616]),
            )
            mismatch = result["mismatches"][0]

            with patch("problem_studio.core.stress.compile_problem_tools", return_value=tools):
                appended = append_stress_case(
                    root,
                    "alpha",
                    "hidden",
                    result["stressRunId"],
                    mismatch["caseId"],
                    mismatch["solutionKey"],
                    mode="generator",
                    name="stress-generator-616",
                )

            cases_yml = (root / "problems" / "alpha" / "generator" / "cases.yml").read_text(
                encoding="utf-8"
            )

        self.assertEqual(appended["mode"], "generator")
        self.assertIn("seed: 616", cases_yml)
        self.assertIn("stress-generator-616", cases_yml)


if __name__ == "__main__":
    unittest.main()
