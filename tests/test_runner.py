"""채점 실행기가 검증기 오류 맥락과 샘플 워밍업 메트릭 계약을 지키는지 검증하는 테스트 모듈입니다."""

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
from judge.core.submission_status import DEFAULT_USER_MEMORY_LIMIT_BYTES, user_memory_limit_bytes
from judge.utils.fs import read_json, write_json
from judge.utils.process import CommandResult


class RunnerErrorMessageTest(unittest.TestCase):
    """실행기 오류 메시지 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_user_memory_limit_defaults_to_2048_mb(self) -> None:
        """문제 메타데이터에 메모리 제한이 없으면 기본 2048MB 제한을 사용합니다."""
        self.assertEqual(user_memory_limit_bytes({}), DEFAULT_USER_MEMORY_LIMIT_BYTES)
        self.assertEqual(user_memory_limit_bytes({"userMemoryLimitMb": 512}), 512 * 1024 * 1024)

    def test_validator_error_includes_context_and_input_preview(self) -> None:
        """검증기 오류 포함 맥락 및 입력 미리보기 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """실행 제출 워밍업 샘플 없이 계산 지표 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
                """실제 최신 캐시 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

                Args:
                    problem_id (Any): 테스트가 생성하거나 조회할 문제 식별자입니다.
                    profile (Any): 검증이나 실행에 사용할 테스트 프로필 이름입니다.
                    cache_root (Any): 캐시 루트 값을 지정하는 인자입니다.

                Returns:
                    Any: 테스트 대상 API가 실제 실행 결과처럼 소비할 수 있는 결정적 결과 데이터입니다.
                """
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
