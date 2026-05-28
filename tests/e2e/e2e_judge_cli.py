from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.e2e.helpers import isolated_runtime, run_judge_cli


def run_dir_from_stdout(runtime: Path, stdout: str) -> Path:
    """Return the run artifact directory mentioned by judge stdout."""
    match = re.search(r"run:\s+(.+)", stdout)
    if not match:
        raise AssertionError(f"run directory not found in stdout:\n{stdout}")
    label = match.group(1).strip()
    path = Path(label)
    if not path.is_absolute():
        path = runtime / "cache" / path
    return path


def show_command_from_stdout(stdout: str) -> tuple[str, str]:
    """Extract `judge show <run> <case>` arguments from judge stdout."""
    for line in stdout.splitlines():
        if "judge show" not in line:
            continue
        parts = line.strip().split()
        return parts[-2], parts[-1]
    raise AssertionError(f"show command not found in stdout:\n{stdout}")


class JudgeCliE2ETest(unittest.TestCase):
    """Subprocess E2E coverage for the judge CLI."""

    def test_generate_reuses_sample_cache(self) -> None:
        with isolated_runtime("alj-judge-cli-generate-e2e-") as (_directory, runtime):
            first = run_judge_cli(
                runtime,
                "generate",
                "06",
                "--profile",
                "sample",
                "--force",
                check=True,
            )
            self.assertIn("Generated data:", first.stdout)
            self.assertTrue(list((runtime / "cache" / "problems" / "06").glob("*/manifest.json")))

            second = run_judge_cli(
                runtime,
                "generate",
                "06",
                "--profile",
                "sample",
                check=True,
            )
            self.assertIn("Using cached data:", second.stdout)

    def test_accepted_run_writes_result_artifact(self) -> None:
        with isolated_runtime("alj-judge-cli-run-e2e-") as (_directory, runtime):
            result = run_judge_cli(
                runtime,
                "--problem",
                "06",
                "--profile",
                "sample",
                "tests/fixtures/accepted.py",
                check=True,
            )

            self.assertIn("Accepted", result.stdout)
            run_dir = run_dir_from_stdout(runtime, result.stdout)
            payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(payload["problemId"], "06")
            self.assertEqual(payload["profile"], "sample")

    def test_wrong_answer_can_show_and_diff_artifacts(self) -> None:
        with isolated_runtime("alj-judge-cli-wrong-e2e-") as (_directory, runtime):
            source = runtime / "wrong.py"
            source.write_text("print(42)\n", encoding="utf-8")

            result = run_judge_cli(
                runtime,
                "--problem",
                "06",
                "--profile",
                "sample",
                str(source),
                check=True,
            )

            self.assertIn("Wrong Answer", result.stdout)
            run_id, case_id = show_command_from_stdout(result.stdout)
            show = run_judge_cli(runtime, "show", run_id, case_id, check=True)
            self.assertIn("== input:", show.stdout)
            self.assertIn("== actual:", show.stdout)
            diff = run_judge_cli(runtime, "diff", run_id, case_id, check=True)
            self.assertIn("--- expected", diff.stdout)
            self.assertIn("+++ actual", diff.stdout)

    def test_compile_error_writes_log(self) -> None:
        with isolated_runtime("alj-judge-cli-compile-error-e2e-") as (_directory, runtime):
            result = run_judge_cli(
                runtime,
                "--problem",
                "06",
                "--profile",
                "sample",
                "tests/fixtures/compile_error.cpp",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("compile error", result.stderr)
            match = re.search(r"log:\s+(.+compile\.log)", result.stderr)
            self.assertIsNotNone(match, result.stderr)
            log_path = runtime / "cache" / match.group(1).strip()
            self.assertTrue(log_path.exists(), result.stderr)

    def test_cases_compile_json_and_invalid_diagnostic(self) -> None:
        with isolated_runtime("alj-judge-cli-cases-e2e-") as (_directory, runtime):
            with tempfile.TemporaryDirectory(prefix="alj-cli-cases-e2e-") as tmp:
                cases = Path(tmp) / "cases.yml"
                cases.write_text(
                    """
profiles:
  sample:
    cases:
      - name: one
        type: fixed
        content: ""
      - name: two
        type: fixed
        content: ""
""".lstrip(),
                    encoding="utf-8",
                )
                json_result = run_judge_cli(
                    runtime,
                    "cases",
                    "compile",
                    "--file",
                    str(cases),
                    "--profile",
                    "sample",
                    "--json",
                    check=True,
                )
                payload = json.loads(json_result.stdout)
                self.assertTrue(payload["valid"])
                self.assertEqual(payload["profiles"][0]["caseCount"], 2)

                cases.write_text(
                    """
profiles:
  hidden:
    cases:
      - matrix:
        vars:
          i: [1]
        item:
          name: "hidden-${i}"
          type: generator
          seed: "${i}"
""".lstrip(),
                    encoding="utf-8",
                )
                invalid = run_judge_cli(
                    runtime,
                    "cases",
                    "compile",
                    "--file",
                    str(cases),
                    "--profile",
                    "hidden",
                )

                self.assertEqual(invalid.returncode, 1)
                self.assertIn("cases.yml: invalid", invalid.stdout)
                self.assertIn("profile hidden, cases[0].matrix", invalid.stdout)
                self.assertIn("matrix must be a mapping, got null", invalid.stdout)

    def test_cache_clear_destructive_workflow_requires_explicit_targets(self) -> None:
        with isolated_runtime("alj-judge-cli-cache-clear-e2e-") as (_directory, runtime):
            run_judge_cli(
                runtime,
                "generate",
                "06",
                "--profile",
                "sample",
                "--force",
                check=True,
            )
            run_judge_cli(
                runtime,
                "--problem",
                "06",
                "--profile",
                "sample",
                "tests/fixtures/wrong.cpp",
                check=True,
            )

            status = run_judge_cli(runtime, "cache", "status", check=True)
            self.assertIn("cache:", status.stdout)

            runs_dry = run_judge_cli(runtime, "cache", "clear", "--runs", "--dry-run", check=True)
            self.assertIn("Dry run: no files deleted.", runs_dry.stdout)
            self.assertTrue(list((runtime / "cache" / "runs").glob("*")))

            runs_clear = run_judge_cli(runtime, "cache", "clear", "--runs", "--yes", check=True)
            self.assertIn("Cache cleared.", runs_clear.stdout)
            self.assertFalse(list((runtime / "cache" / "runs").glob("*")))

            problem_dry = run_judge_cli(
                runtime,
                "cache",
                "clear",
                "--problem",
                "06",
                "--profile",
                "sample",
                "--dry-run",
                check=True,
            )
            self.assertIn("Dry run: no files deleted.", problem_dry.stdout)
            self.assertTrue(list((runtime / "cache" / "problems" / "06").glob("*")))

            all_clear = run_judge_cli(runtime, "cache", "clear", "--all", "--yes", check=True)
            self.assertIn("Cache cleared.", all_clear.stdout)
            no_target = run_judge_cli(runtime, "cache", "clear", "--dry-run")
            self.assertNotEqual(no_target.returncode, 0)
            self.assertIn("choose at least one target", no_target.stderr)

    def test_cpp_accepted_run_is_supported_by_cli_e2e(self) -> None:
        with isolated_runtime("alj-judge-cli-cpp-e2e-") as (_directory, runtime):
            result = run_judge_cli(
                runtime,
                "--problem",
                "06",
                "--profile",
                "sample",
                "problems/algorithm-package/problems/06/solutions/main_solution.ac.cpp",
                check=True,
            )
            self.assertIn("Accepted", result.stdout)

    @unittest.skipUnless(
        shutil.which("javac") and shutil.which("java"),
        "Java toolchain is not installed",
    )
    def test_java_accepted_run_is_supported_by_cli_e2e(self) -> None:
        with isolated_runtime("alj-judge-cli-java-e2e-") as (_directory, runtime):
            result = run_judge_cli(
                runtime,
                "--problem",
                "06",
                "--profile",
                "sample",
                "tests/fixtures/Main.java",
                check=True,
            )
            self.assertIn("Accepted", result.stdout)

    def test_show_parts_and_cases_expanded_preview_cli_options(self) -> None:
        with isolated_runtime("alj-judge-cli-show-cases-e2e-") as (_directory, runtime):
            result = run_judge_cli(
                runtime,
                "--problem",
                "06",
                "--profile",
                "sample",
                "tests/fixtures/wrong.cpp",
                check=True,
            )
            run_id, case_id = show_command_from_stdout(result.stdout)

            input_part = run_judge_cli(runtime, "show", run_id, case_id, "--input", check=True)
            self.assertIn("== input:", input_part.stdout)
            self.assertNotIn("== expected:", input_part.stdout)
            expected_part = run_judge_cli(
                runtime, "show", run_id, case_id, "--expected", check=True
            )
            self.assertIn("== expected:", expected_part.stdout)
            self.assertNotIn("== actual:", expected_part.stdout)
            actual_part = run_judge_cli(runtime, "show", run_id, case_id, "--actual", check=True)
            self.assertIn("== actual:", actual_part.stdout)
            self.assertIn("42", actual_part.stdout)

            expanded = run_judge_cli(
                runtime,
                "cases",
                "compile",
                "06",
                "--profile",
                "sample",
                "--expanded",
                "--max-preview",
                "1",
                check=True,
            )
            self.assertIn("cases.yml: ok", expanded.stdout)
            self.assertIn("profile sample:", expanded.stdout)
            self.assertRegex(expanded.stdout, r"\s001\s")


if __name__ == "__main__":
    unittest.main()
