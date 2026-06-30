"""실제 judge 명령줄 도구를 하위 프로세스로 실행해 캐시, 산출물, 오류 표시 계약을 검증하는 종단 간 테스트 모듈입니다."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.e2e.helpers import ROOT, e2e_project_root, isolated_runtime, judge_env, run_judge_cli


def run_dir_from_stdout(runtime: Path, stdout: str) -> Path:
    """judge 실행 출력에서 산출물 디렉터리 위치를 찾아 후속 조회 테스트에 전달합니다.

    Args:
        runtime (Path): 격리된 데이터 홈과 캐시 홈을 담은 런타임 디렉터리입니다.
        stdout (str): 명령 실행 결과에서 추출한 표준 출력 문자열입니다.

    Returns:
        Path: 명령 출력에서 추출한 실행 산출물 디렉터리 경로입니다.
    """
    match = re.search(r"run:\s+(.+)", stdout)
    if not match:
        raise AssertionError(f"run directory not found in stdout:\n{stdout}")
    label = match.group(1).strip()
    path = Path(label)
    if not path.is_absolute():
        path = runtime / "cache" / path
    return path


def show_command_from_stdout(stdout: str) -> tuple[str, str]:
    """오답 출력에 안내된 judge show 명령 인자를 추출해 산출물 조회 흐름을 검증합니다.

    Args:
        stdout (str): 명령 실행 결과에서 추출한 표준 출력 문자열입니다.

    Returns:
        tuple[str, str]: judge show 명령에 다시 전달할 실행 식별자와 케이스 식별자입니다.
    """
    for line in stdout.splitlines():
        if "judge show" not in line:
            continue
        parts = line.strip().split()
        return parts[-2], parts[-1]
    raise AssertionError(f"show command not found in stdout:\n{stdout}")


class JudgeCliE2ETest(unittest.TestCase):
    """채점기 명령줄 종단 간 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_judge_env_defaults_to_isolated_project_root(self) -> None:
        """judge_env 기본 project root가 실제 저장소가 아닌 임시 프로젝트인지 검증합니다."""
        with isolated_runtime("alj-judge-cli-env-e2e-") as (_directory, runtime):
            env = judge_env(runtime)
            project_root = Path(env["ALJ_PROJECT_ROOT"])

            self.assertEqual(project_root, e2e_project_root(runtime).resolve())
            self.assertNotEqual(project_root, ROOT.resolve())
            self.assertTrue((project_root / "problems" / "06" / "problem.json").exists())

            with self.assertRaises(RuntimeError):
                judge_env(runtime, project_root=ROOT)

    def test_generate_reuses_sample_cache(self) -> None:
        """생성 재사용 샘플 캐시 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """정답 실행 쓰기 결과 산출물 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """오답 답안 가능 조회 및 차이 산출물 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """컴파일 오류 쓰기 로그 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """케이스 컴파일 JSON 및 잘못된 진단 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """캐시 삭제 파괴적 절차 요구 명시적 대상 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """C++ 정답 실행 지원 명령줄 종단 간 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-cli-cpp-e2e-") as (_directory, runtime):
            source = (
                e2e_project_root(runtime)
                / "problems"
                / "06"
                / "solutions"
                / "main_solution.ac.cpp"
            )
            result = run_judge_cli(
                runtime,
                "--problem",
                "06",
                "--profile",
                "sample",
                str(source),
                check=True,
            )
            self.assertIn("Accepted", result.stdout)

    @unittest.skipUnless(
        shutil.which("javac") and shutil.which("java"),
        "Java toolchain is not installed",
    )
    def test_java_accepted_run_is_supported_by_cli_e2e(self) -> None:
        """Java 정답 실행 지원 명령줄 종단 간 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """조회 부분 및 케이스 확장 미리보기 명령줄 옵션 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
