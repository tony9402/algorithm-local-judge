"""judge 명령줄의 실행, 생성, 캐시, 진단, 설치 옵션 계약을 스모크 테스트로 검증하는 모듈입니다."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from judge.cli_parser import build_parser

ROOT = Path(__file__).resolve().parents[1]
JUDGE = [sys.executable, "-m", "judge"]
PROBLEM_PACKAGE_ROOT = ROOT / "problems" / "algorithm-package"
PROBLEM_SOURCE_ROOT = PROBLEM_PACKAGE_ROOT / "problems"
TEST_TOOL_COMPILE_TIMEOUT_MIN_MS = "30000"
ISOLATED_RUNTIME = tempfile.TemporaryDirectory(prefix="alj-unit-cli-runtime-")
ISOLATED_PROJECT_ROOT = Path(ISOLATED_RUNTIME.name) / "project"
shutil.copytree(PROBLEM_SOURCE_ROOT / "06", ISOLATED_PROJECT_ROOT / "problems" / "06")
shutil.copy2(ROOT / "testlib.h", ISOLATED_PROJECT_ROOT / "testlib.h")


def run_judge(
    *args: str,
    check: bool = False,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """채점기 흐름을 격리된 환경에서 실행해 종료 코드와 출력을 검증할 수 있게 합니다.

    Args:
        args (str): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
        check (bool): 하위 프로세스 실패를 예외로 처리할지 결정하는 플래그입니다.
        extra_env (dict[str, str] | None): 격리 실행 환경에 추가로 주입할 환경 변수입니다.

    Returns:
        subprocess.CompletedProcess[str]: judge 명령줄 실행 결과 객체입니다.
    """
    env = os.environ.copy()
    env["ALJ_PROJECT_ROOT"] = str(ISOLATED_PROJECT_ROOT)
    env["ALJ_DATA_HOME"] = str(Path(ISOLATED_RUNTIME.name) / "data")
    env["ALJ_CACHE_HOME"] = str(Path(ISOLATED_RUNTIME.name) / "cache")
    env["ALJ_PYTHON"] = sys.executable
    env["ALJ_TOOL_COMPILE_TIMEOUT_MIN_MS"] = TEST_TOOL_COMPILE_TIMEOUT_MIN_MS
    if extra_env:
        env.update(extra_env)
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
    """채점기 명령줄 스모크 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_problem_metadata_has_no_forbidden_keys(self) -> None:
        """문제 메타데이터 보유 없는 금지된 키 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        problem_dir = PROBLEM_SOURCE_ROOT / "06"
        metadata = json.loads((problem_dir / "problem.json").read_text(encoding="utf-8"))
        forbidden = {"externalId", "externalUrl", "externalPlatform", "platform"}
        self.assertFalse(forbidden.intersection(metadata))
        self.assertFalse(
            [key for key in metadata if key != "problemId" and key.lower().endswith("id")]
        )
        for relative_path in metadata["tools"].values():
            self.assertTrue((problem_dir / relative_path).exists())
        self.assertTrue((ROOT / "commons/generate.py").exists())
        self.assertFalse((problem_dir / "generate.py").exists())
        self.assertIn("generatorConfig", metadata["tools"])

    def test_generate_and_reuse_sample_cache(self) -> None:
        """생성 및 재사용 샘플 캐시 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        first = run_judge("generate", "06", "--profile", "sample", "--force", check=True)
        self.assertIn("Generated data:", first.stdout)
        second = run_judge("generate", "06", "--profile", "sample", check=True)
        self.assertIn("Using cached data:", second.stdout)

    def test_solution_is_accepted_with_default_file_command(self) -> None:
        """솔루션 정답 기본 파일 명령 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge(
            "--profile",
            "sample",
            str(ISOLATED_PROJECT_ROOT / "problems" / "06" / "solutions" / "main_solution.ac.cpp"),
            check=True,
        )
        self.assertIn("Accepted", result.stdout)

    def test_python_solution_is_accepted(self) -> None:
        """Python 솔루션 정답 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge(
            "--problem", "06", "--profile", "sample", "tests/fixtures/accepted.py", check=True
        )
        self.assertIn("Accepted", result.stdout)

    def test_pypy_solution_is_accepted_with_configured_runtime(self) -> None:
        """PyPy 언어 선택이 ALJ_PYPY 런타임을 사용하고 결과 언어를 보존하는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-fake-pypy-") as tmp:
            fake_pypy = Path(tmp) / "pypy3"
            fake_pypy.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
            fake_pypy.chmod(0o755)

            result = run_judge(
                "--problem",
                "06",
                "--profile",
                "sample",
                "--language",
                "pypy",
                "tests/fixtures/accepted.py",
                check=True,
                extra_env={"ALJ_PYPY": str(fake_pypy)},
            )

        self.assertIn("Accepted", result.stdout)
        run_line = next(line for line in result.stdout.splitlines() if line.startswith("run: "))
        run_dir = ISOLATED_PROJECT_ROOT / run_line.removeprefix("run: ").strip()
        payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["language"], "pypy")

    @unittest.skipUnless(
        shutil.which("javac") and shutil.which("java"),
        "Java toolchain is not installed",
    )
    def test_java_solution_is_accepted(self) -> None:
        """Java 솔루션 정답 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge(
            "--problem", "06", "--profile", "sample", "tests/fixtures/Main.java", check=True
        )
        self.assertIn("Accepted", result.stdout)

    def test_wrong_answer_writes_artifacts_and_can_show_diff(self) -> None:
        """오답 답안 쓰기 산출물 및 가능 조회 차이 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """컴파일 오류 쓰기 로그 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge(
            "--problem", "06", "--profile", "sample", "tests/fixtures/compile_error.cpp"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("compile error", result.stderr)
        self.assertIn("compile.log", result.stderr)

    def test_cache_status_and_dry_run(self) -> None:
        """캐시 상태 및 드라이런 실행 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        run_judge("generate", "06", "--profile", "sample", check=True)
        status = run_judge("cache", "status", check=True)
        self.assertIn("cache:", status.stdout)
        dry_run = run_judge("cache", "clear", "--all", "--dry-run", check=True)
        self.assertIn("Dry run", dry_run.stdout)

    def test_compile_command_smoke(self) -> None:
        """컴파일 명령 스모크 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge("compile", "06", check=True)
        self.assertIn("Compiled tools for problem 06", result.stdout)

    def test_cases_compile_problem_profile_smoke(self) -> None:
        """케이스 컴파일 문제 프로필 스모크 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge("cases", "compile", "06", "--profile", "sample", check=True)

        self.assertIn("cases.yml: ok", result.stdout)
        self.assertIn("profile sample:", result.stdout)

    def test_cases_compile_file_json_and_preview(self) -> None:
        """케이스 컴파일 파일 JSON 및 미리보기 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """케이스 컴파일 잘못된 파일 반환 하나 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """케이스 컴파일 잘못된 JSON 및 인자 오류 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """캐시 삭제 요구 대상 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge("cache", "clear", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("choose at least one target", result.stderr)

    def test_cache_clear_problem_and_runs_dry_run(self) -> None:
        """캐시 삭제 문제 및 실행 드라이런 실행 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        run_judge("generate", "06", "--profile", "sample", check=True)
        run_judge("--problem", "06", "--profile", "sample", "tests/fixtures/wrong.cpp", check=True)
        problem = run_judge("cache", "clear", "--problem", "06", "--dry-run", check=True)
        self.assertIn("Dry run", problem.stdout)
        runs = run_judge("cache", "clear", "--runs", "--dry-run", check=True)
        self.assertIn("Dry run", runs.stdout)

    def test_rejects_run_global_options_before_non_run_commands(self) -> None:
        """거부 실행 전역 옵션 전에 비 실행 명령 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        generate = run_judge("--profile", "sample", "generate", "06")
        self.assertNotEqual(generate.returncode, 0)
        self.assertIn("global --profile can only be used with run", generate.stderr)

        cache = run_judge("--problem", "06", "cache", "clear", "--dry-run")
        self.assertNotEqual(cache.returncode, 0)
        self.assertIn("global --problem can only be used with run", cache.stderr)

    def test_rejects_abbreviated_global_options(self) -> None:
        """거부 축약 전역 옵션 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge(
            "--prof",
            "sample",
            "problems/algorithm-package/problems/06/solutions/main_solution.ac.cpp",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_problem_id_inference_failure_is_actionable(self) -> None:
        """문제 식별자 추론 실패 조치 가능한 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge("--profile", "sample", "tests/fixtures/wrong.cpp")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not infer problem id", result.stderr)
        self.assertIn("--problem 06", result.stderr)

    def test_list_problems(self) -> None:
        """목록 문제 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge("list", check=True)
        self.assertIn("Problems:", result.stdout)
        self.assertIn("06", result.stdout)

    def test_doctor_reports_local_environment(self) -> None:
        """진단 명령 보고 로컬 환경 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-doctor-") as tmp:
            tmp_path = Path(tmp)
            result = run_judge(
                "doctor",
                check=True,
                extra_env={
                    "ALJ_DATA_HOME": str(tmp_path / "data"),
                    "ALJ_CACHE_HOME": str(tmp_path / "cache"),
                },
            )

        self.assertIn("Judge doctor:", result.stdout)
        self.assertIn("Platform:", result.stdout)
        self.assertIn("Python: OK", result.stdout)
        self.assertIn("Tools:", result.stdout)
        self.assertIn("C++ compiler:", result.stdout)
        self.assertIn("Java compiler:", result.stdout)
        self.assertIn("PyPy runtime:", result.stdout)
        self.assertIn("Git:", result.stdout)
        self.assertIn("Paths:", result.stdout)
        self.assertIn("Installed packs: 0", result.stdout)
        self.assertIn("Official repository: OK tony9402/algorithm-package", result.stdout)

    def test_doctor_verbose_and_json_output(self) -> None:
        """진단 명령 상세 및 JSON 출력 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-doctor-json-") as tmp:
            tmp_path = Path(tmp)
            env = {
                "ALJ_DATA_HOME": str(tmp_path / "data"),
                "ALJ_CACHE_HOME": str(tmp_path / "cache"),
            }
            verbose = run_judge("doctor", "--verbose", check=True, extra_env=env)
            json_result = run_judge("doctor", "--json", check=True, extra_env=env)

        self.assertIn("exists:", verbose.stdout)
        payload = json.loads(json_result.stdout)
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertIn(payload["status"], {"ok", "warning"})
        self.assertEqual(payload["python"]["status"], "ok")
        self.assertIn("cpp", payload["tools"])
        self.assertIn("pypyRuntime", payload["tools"])
        self.assertIn(payload["tools"]["cpp"]["status"], {"ok", "missing"})
        self.assertIn(payload["tools"]["pypyRuntime"]["status"], {"ok", "missing"})
        self.assertIn("projectRoot", payload["paths"])
        self.assertEqual(payload["installedPacks"]["count"], 0)
        self.assertEqual(
            payload["officialRepository"]["repository"],
            "tony9402/algorithm-package",
        )

    def test_doctor_reports_invalid_official_repository_without_crashing(self) -> None:
        """진단 명령 보고 잘못된 공식 저장소 없이 중단 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge(
            "doctor",
            "--json",
            check=True,
            extra_env={"ALJ_OFFICIAL_PACK_REPOSITORY": "not a repository"},
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["officialRepository"]["status"], "warning")
        self.assertIn("official repository", payload["officialRepository"]["error"])

    def test_problem_install_checksum_options_are_parsed(self) -> None:
        """문제 설치 체크섬 옵션 파싱 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        parser = build_parser()
        checksum = "a" * 64

        args = parser.parse_args(
            [
                "problem",
                "install",
                "https://example.com/basic.aljpack",
                "--checksum",
                checksum,
            ]
        )
        self.assertEqual(args.command, "problem")
        self.assertEqual(args.problem_command, "install")
        self.assertEqual(args.source, "https://example.com/basic.aljpack")
        self.assertEqual(args.checksum, checksum)
        self.assertIsNone(args.checksum_url)

        args = parser.parse_args(
            [
                "problem",
                "install",
                "https://example.com/basic.aljpack",
                "--checksum-url",
                "https://example.com/basic.aljpack.sha256",
            ]
        )
        self.assertIsNone(args.checksum)
        self.assertEqual(args.checksum_url, "https://example.com/basic.aljpack.sha256")

    def test_pack_trust_repository_management(self) -> None:
        """패키지 신뢰 저장소 관리 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-pack-trust-cli-") as tmp:
            env = {"ALJ_DATA_HOME": str(Path(tmp) / "data")}

            listed = run_judge("pack", "trust", "list", check=True, extra_env=env)
            self.assertIn("tony9402/algorithm-package (default)", listed.stdout)

            added = run_judge(
                "pack",
                "trust",
                "add",
                "example/problems",
                check=True,
                extra_env=env,
            )
            self.assertIn("example/problems", added.stdout)

            listed = run_judge("pack", "trust", "list", check=True, extra_env=env)
            self.assertIn("example/problems (user)", listed.stdout)

            removed = run_judge(
                "pack",
                "trust",
                "remove",
                "example/problems",
                check=True,
                extra_env=env,
            )
            self.assertIn("example/problems", removed.stdout)

    def test_validate_problem_sequence_reports_missing_start(self) -> None:
        """검증 문제 순서 보고 누락 시작 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-sequence-test-") as tmp:
            project_root = Path(tmp)
            shutil.copytree(PROBLEM_SOURCE_ROOT / "06", project_root / "problems" / "06")
            result = run_judge(
                "list",
                "--validate",
                extra_env={
                    "ALJ_PROJECT_ROOT": str(project_root),
                    "ALJ_DATA_HOME": str(project_root / "data"),
                },
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("problem numbering must start at 1", result.stderr)

    def test_rejects_unsafe_problem_id(self) -> None:
        """거부 안전하지 않은 문제 식별자 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        result = run_judge("cache", "clear", "--problem", "../06", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid problem id", result.stderr)


if __name__ == "__main__":
    unittest.main()
