from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from judge.core.compiler import PreparedSubmission
from judge.core.errors import JudgeError
from judge.core.runner import validator_check
from judge.core.submission import run_submission
from judge.utils.fs import read_json, write_json
from judge.utils.process import CommandResult


class RunnerErrorMessageTest(unittest.TestCase):
    """Runtime helper errors should be useful in the web UI."""

    def test_validator_error_includes_context_and_input_preview(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-runner-") as tmp:
            root = Path(tmp)
            input_path = root / "001.in"
            input_path.write_text("10 20\n3 4\n", encoding="utf-8")

            with patch(
                "judge.core.runner.run_command",
                return_value=(1, b"", b"FAIL Expected EOF (stdin, line 1)\n"),
            ):
                with self.assertRaises(JudgeError) as raised:
                    validator_check(
                        root / "validator",
                        input_path,
                        5000,
                        profile="hidden",
                        case_index=1,
                        case_total=3,
                        root=root,
                    )

        message = str(raised.exception)
        self.assertIn("validator failed for 001.in: FAIL Expected EOF", message)
        self.assertIn("profile: hidden", message)
        self.assertIn("case: 1/3", message)
        self.assertIn("input: 001.in", message)
        self.assertIn("validator stopped reading before the generated input ended", message)
        self.assertIn("input preview:", message)
        self.assertIn("   1 | 10 20", message)
        self.assertIn("   2 | 3 4", message)

    def test_run_submission_warms_up_with_sample_without_counting_metrics(self) -> None:
        """A warmup profile should run before measured cases and stay out of maxTimeMs."""
        with tempfile.TemporaryDirectory(prefix="alj-runner-") as tmp:
            root = Path(tmp)
            source = root / "solution.cpp"
            source.write_text("int main() { return 0; }\n", encoding="utf-8")
            problem = root / "problems" / "01"
            problem.mkdir(parents=True)
            write_json(
                problem / "problem.json",
                {
                    "schemaVersion": 1,
                    "problemId": "01",
                    "title": "warmup",
                    "version": 1,
                    "defaultProfile": "hidden",
                    "limits": {"userTimeoutMs": 2000, "compileTimeoutMs": 5000},
                },
            )
            sample_dir = root / ".judge-cache" / "sample-data"
            hidden_dir = root / ".judge-cache" / "hidden-data"
            for data_dir, profile, case_ids in (
                (sample_dir, "sample", ["001"]),
                (hidden_dir, "hidden", ["101", "102"]),
            ):
                (data_dir / "cases").mkdir(parents=True)
                cases = []
                for case_id in case_ids:
                    (data_dir / "cases" / f"{case_id}.in").write_text(
                        f"{case_id}\n",
                        encoding="utf-8",
                    )
                    (data_dir / "cases" / f"{case_id}.out").write_text(
                        f"{case_id}\n",
                        encoding="utf-8",
                    )
                    cases.append(
                        {
                            "id": case_id,
                            "input": f"cases/{case_id}.in",
                            "answer": f"cases/{case_id}.out",
                        }
                    )
                (data_dir / "manifest.json").write_text(
                    json.dumps({"profile": profile, "cases": cases}),
                    encoding="utf-8",
                )

            def fake_latest_cache(problem_id, profile, cache_root):
                self.assertEqual(problem_id, "01")
                self.assertEqual(cache_root, root)
                return {"sample": sample_dir, "hidden": hidden_dir}[profile]

            command_results = [
                CommandResult(0, b"", b"", 99, 1000),
                CommandResult(0, b"", b"", 7, 2000),
                CommandResult(0, b"", b"", 11, 3000),
            ]

            with (
                patch("judge.core.submission.ensure_cases_compiled"),
                patch(
                    "judge.core.submission.prepare_user_submission",
                    return_value=PreparedSubmission(["solution"], "cpp"),
                ),
                patch("judge.core.submission.latest_cache_for", side_effect=fake_latest_cache),
                patch(
                    "judge.core.submission.compile_problem_tools",
                    return_value={"checker": root / "checker"},
                ),
                patch("judge.core.submission.checker_compare", return_value=(0, "")),
                patch(
                    "judge.core.submission.run_command_result",
                    side_effect=command_results,
                ) as mocked_run,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                run_dir = run_submission(
                    source,
                    "01",
                    "hidden",
                    root=root,
                    warmup_profile="sample",
                )

            run_inputs = [call.kwargs["input_path"] for call in mocked_run.call_args_list]
            self.assertEqual(
                run_inputs,
                [
                    sample_dir / "cases" / "001.in",
                    hidden_dir / "cases" / "101.in",
                    hidden_dir / "cases" / "102.in",
                ],
            )
            result = read_json(run_dir / "result.json")
            self.assertEqual(result["metrics"]["maxTimeMs"], 11)
            self.assertEqual([case["timeMs"] for case in result["cases"]], [7, 11])
            self.assertEqual(result["warmup"]["profile"], "sample")
            self.assertEqual(result["warmup"]["timeMs"], 99)


if __name__ == "__main__":
    unittest.main()
