from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JUDGE = [sys.executable, "-m", "judge"]


def run_judge(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run the judge CLI in the repository root for smoke tests."""
    env = os.environ.copy()
    env["ALJ_CACHE_HOME"] = str(ROOT / ".judge-cache")
    env["ALJ_PYTHON"] = sys.executable
    result = subprocess.run(
        [*JUDGE, *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


class JudgeCliSmokeTest(unittest.TestCase):
    """End-to-end smoke tests for the judge command line interface."""

    def test_problem_metadata_has_no_forbidden_keys(self) -> None:
        """Problem metadata should avoid external platform-specific fields."""
        metadata = json.loads((ROOT / "problems/06/problem.json").read_text(encoding="utf-8"))
        forbidden = {"externalId", "externalUrl", "externalPlatform", "platform"}
        self.assertFalse(forbidden.intersection(metadata))
        self.assertFalse(
            [key for key in metadata if key != "problemId" and key.lower().endswith("id")]
        )
        for relative_path in metadata["tools"].values():
            self.assertTrue((ROOT / "problems/06" / relative_path).exists())
        self.assertTrue((ROOT / "commons/generate.py").exists())
        self.assertFalse((ROOT / "problems/06/generate.py").exists())
        self.assertIn("generatorConfig", metadata["tools"])

    def test_generate_and_reuse_sample_cache(self) -> None:
        """Generating sample data twice should reuse a valid cache."""
        first = run_judge("generate", "06", "--profile", "sample", "--force", check=True)
        self.assertIn("Generated data:", first.stdout)
        second = run_judge("generate", "06", "--profile", "sample", check=True)
        self.assertIn("Using cached data:", second.stdout)

    def test_solution_is_accepted_with_default_file_command(self) -> None:
        """Implicit run syntax should accept the reference solution."""
        result = run_judge(
            "--profile", "sample", "problems/06/solutions/main_solution.ac.cpp", check=True
        )
        self.assertIn("Accepted", result.stdout)

    def test_python_solution_is_accepted(self) -> None:
        """Python submissions should run through the same judge flow."""
        result = run_judge(
            "--problem", "06", "--profile", "sample", "tests/fixtures/accepted.py", check=True
        )
        self.assertIn("Accepted", result.stdout)

    @unittest.skipUnless(
        shutil.which("javac") and shutil.which("java"),
        "Java toolchain is not installed",
    )
    def test_java_solution_is_accepted(self) -> None:
        """Java submissions should compile and run through the judge flow."""
        result = run_judge(
            "--problem", "06", "--profile", "sample", "tests/fixtures/Main.java", check=True
        )
        self.assertIn("Accepted", result.stdout)

    def test_wrong_answer_writes_artifacts_and_can_show_diff(self) -> None:
        """Wrong answers should save artifacts that show and diff can read."""
        result = run_judge(
            "--problem", "06", "--profile", "sample", "tests/fixtures/wrong.cpp", check=True
        )
        self.assertIn("Wrong Answer", result.stdout)
        run_id = None
        case_id = None
        for line in result.stdout.splitlines():
            if "judge show" in line:
                parts = line.strip().split()
                run_id = parts[-2]
                case_id = parts[-1]
        self.assertIsNotNone(run_id)
        self.assertIsNotNone(case_id)
        show = run_judge("show", run_id, case_id, check=True)
        self.assertIn("== input:", show.stdout)
        diff = run_judge("diff", run_id, case_id, check=True)
        self.assertIn("--- expected", diff.stdout)

    def test_compile_error_writes_log(self) -> None:
        """Compile errors should fail the run and point to compile.log."""
        result = run_judge(
            "--problem", "06", "--profile", "sample", "tests/fixtures/compile_error.cpp"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("compile error", result.stderr)
        self.assertIn("compile.log", result.stderr)

    def test_cache_status_and_dry_run(self) -> None:
        """Cache status and all-cache dry-run should report safely."""
        run_judge("generate", "06", "--profile", "sample", check=True)
        status = run_judge("cache", "status", check=True)
        self.assertIn("cache:", status.stdout)
        dry_run = run_judge("cache", "clear", "--all", "--dry-run", check=True)
        self.assertIn("Dry run", dry_run.stdout)

    def test_compile_command_smoke(self) -> None:
        """The compile command should build problem tools explicitly."""
        result = run_judge("compile", "06", check=True)
        self.assertIn("Compiled tools for problem 06", result.stdout)

    def test_cases_compile_problem_profile_smoke(self) -> None:
        """The cases compile command should validate one problem profile."""
        result = run_judge("cases", "compile", "06", "--profile", "sample", check=True)

        self.assertIn("cases.yml: ok", result.stdout)
        self.assertIn("profile sample:", result.stdout)

    def test_cases_compile_file_json_and_preview(self) -> None:
        """Cases compile should support --file, JSON output, and preview limits."""
        with tempfile.TemporaryDirectory(prefix="alj-cli-cases-") as tmp:
            path = Path(tmp) / "cases.yml"
            path.write_text(
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

            json_result = run_judge(
                "cases",
                "compile",
                "--file",
                str(path),
                "--profile",
                "sample",
                "--json",
                check=True,
            )
            payload = json.loads(json_result.stdout)
            self.assertTrue(payload["valid"])
            self.assertEqual(payload["profiles"][0]["caseCount"], 2)

            preview = run_judge(
                "cases",
                "compile",
                "--file",
                str(path),
                "--profile",
                "sample",
                "--expanded",
                "--max-preview",
                "1",
                check=True,
            )
            self.assertIn("001 one fixed", preview.stdout)
            self.assertIn("... 1 more case(s)", preview.stdout)

    def test_cases_compile_invalid_file_returns_one(self) -> None:
        """Invalid cases.yml should return exit code 1 with a diagnostic."""
        with tempfile.TemporaryDirectory(prefix="alj-cli-cases-") as tmp:
            path = Path(tmp) / "cases.yml"
            path.write_text(
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

            result = run_judge("cases", "compile", "--file", str(path), "--profile", "hidden")

            self.assertEqual(result.returncode, 1)
            self.assertIn("cases.yml: invalid", result.stdout)
            self.assertIn("profile hidden, cases[0].matrix", result.stdout)
            self.assertIn("matrix must be a mapping, got null", result.stdout)

    def test_cases_compile_invalid_json_and_argument_errors(self) -> None:
        """CLI edge cases should keep predictable exit codes and output channels."""
        with tempfile.TemporaryDirectory(prefix="alj-cli-cases-") as tmp:
            path = Path(tmp) / "cases.yml"
            path.write_text(
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

            invalid_json = run_judge(
                "cases",
                "compile",
                "--file",
                str(path),
                "--profile",
                "hidden",
                "--json",
            )
            payload = json.loads(invalid_json.stdout)
            self.assertEqual(invalid_json.returncode, 1)
            self.assertFalse(payload["valid"])
            self.assertEqual(invalid_json.stderr, "")

            missing_target = run_judge("cases", "compile")
            self.assertEqual(missing_target.returncode, 1)
            self.assertIn("choose exactly one target", missing_target.stderr)

            duplicate_target = run_judge("cases", "compile", "06", "--file", str(path))
            self.assertEqual(duplicate_target.returncode, 1)
            self.assertIn("choose exactly one target", duplicate_target.stderr)

            bad_preview = run_judge("cases", "compile", "--file", str(path), "--max-preview", "0")
            self.assertEqual(bad_preview.returncode, 1)
            self.assertIn("--max-preview must be greater than zero", bad_preview.stderr)

            global_profile = run_judge("--profile", "sample", "cases", "compile", "06")
            self.assertEqual(global_profile.returncode, 1)
            self.assertIn("global --profile can only be used with run", global_profile.stderr)

    def test_cache_clear_requires_target(self) -> None:
        """Cache clear should reject invocations without a target."""
        result = run_judge("cache", "clear", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("choose at least one target", result.stderr)

    def test_cache_clear_problem_and_runs_dry_run(self) -> None:
        """Problem and runs cache targets should support dry-run output."""
        run_judge("generate", "06", "--profile", "sample", check=True)
        run_judge("--problem", "06", "--profile", "sample", "tests/fixtures/wrong.cpp", check=True)
        problem = run_judge("cache", "clear", "--problem", "06", "--dry-run", check=True)
        self.assertIn("Dry run", problem.stdout)
        runs = run_judge("cache", "clear", "--runs", "--dry-run", check=True)
        self.assertIn("Dry run", runs.stdout)

    def test_rejects_run_global_options_before_non_run_commands(self) -> None:
        """Run-only global options should fail before non-run commands."""
        generate = run_judge("--profile", "sample", "generate", "06")
        self.assertNotEqual(generate.returncode, 0)
        self.assertIn("global --profile can only be used with run", generate.stderr)

        cache = run_judge("--problem", "06", "cache", "clear", "--dry-run")
        self.assertNotEqual(cache.returncode, 0)
        self.assertIn("global --problem can only be used with run", cache.stderr)

    def test_rejects_abbreviated_global_options(self) -> None:
        """Long option abbreviations should be disabled for consistency."""
        result = run_judge("--prof", "sample", "problems/06/solutions/main_solution.ac.cpp")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_problem_id_inference_failure_is_actionable(self) -> None:
        """Inference failures should tell users how to pass a problem id."""
        result = run_judge("--profile", "sample", "tests/fixtures/wrong.cpp")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not infer problem id", result.stderr)
        self.assertIn("--problem 06", result.stderr)

    def test_list_problems(self) -> None:
        """The list command should show discovered problem ids."""
        result = run_judge("list", check=True)
        self.assertIn("Problems:", result.stdout)
        self.assertIn("06", result.stdout)

    def test_validate_problem_sequence_reports_missing_start(self) -> None:
        """Problem numbering validation should report the missing starting id."""
        result = run_judge("list", "--validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("problem numbering must start at 1", result.stderr)

    def test_rejects_unsafe_problem_id(self) -> None:
        """Unsafe problem ids should be rejected before cache path access."""
        result = run_judge("cache", "clear", "--problem", "../06", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid problem id", result.stderr)


if __name__ == "__main__":
    unittest.main()
