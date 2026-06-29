"""문제 스튜디오 스트레스 실행기가 난수, 제한 시간, 불일치 산출물, 고정 케이스 추가 계약을 지키는지 검증하는 모듈입니다."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from commons.job_queue import CancelToken, JobCancelledError
from alj_core.errors import JudgeError
from alj_core.utils.fs import write_json
from problem_studio.core.stress import append_stress_case, stress_test_solutions


def write_executable(path: Path, content: str) -> Path:
    """테스트용 실행 파일을 작성하고 실행 권한을 부여해 외부 도구 호출을 재현합니다.

    Args:
        path (Path): 테스트가 조작할 파일 또는 문제 스튜디오 내부 경로입니다.
        content (str): 픽스처 파일에 기록할 소스 코드나 텍스트 내용입니다.

    Returns:
        Path: 테스트가 생성하거나 조회한 파일 시스템 경로입니다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def create_stress_problem(root: Path) -> tuple[Path, dict[str, Path]]:
    """스트레스 문제 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        root (Path): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.

    Returns:
        tuple[Path, dict[str, Path]]: 스트레스 실행 테스트에 사용할 문제 디렉터리 경로입니다.
    """
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
            "#!/usr/bin/env python3\nimport sys\nsys.stdin.read()\n",
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
            "#!/usr/bin/env python3\nimport sys\nsys.stdout.write(sys.stdin.read())\n",
        ),
    }
    return problem, tools


class CyclingRng:
    """스트레스 실행 테스트가 예측 가능한 난수 순서를 사용하도록 값을 순환 반환하는 난수 대역입니다."""

    def __init__(self, values: list[int]) -> None:
        """테스트용 난수 대역이 순환 반환할 값을 초기화합니다.

        Args:
            values (list[int]): 난수 대역이 순서대로 반환할 값 목록입니다.
        """
        self.values = list(values)

    def randrange(self, _start: int, _stop: int) -> int:
        """스트레스 실행기가 요청한 정수 난수 대신 준비된 값을 순서대로 반환합니다.

        Args:
            _start (int): 난수 API 시그니처를 맞추기 위해 받는 시작 범위입니다.
            _stop (int): 난수 API 시그니처를 맞추기 위해 받는 종료 범위입니다.

        Returns:
            int: 테스트 흐름에서 비교하거나 사용할 정수 값입니다.
        """
        return self.values.pop(0)

    def choice(self, values):
        """스트레스 실행기가 컬렉션에서 임의 선택을 요청할 때 준비된 값을 순서대로 반환합니다.

        Args:
            values (Any): 난수 대역이 순서대로 반환할 값 목록입니다.

        Returns:
            Any: 호출자가 다음 검증 단계에서 사용할 결과 값입니다.
        """
        return values[0]


class ProblemStudioStressTest(unittest.TestCase):
    """문제 스튜디오 스트레스 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def run_with_tools(self, root: Path, tools: dict[str, Path], **kwargs):
        """도구 흐름을 격리된 환경에서 실행해 종료 코드와 출력을 검증할 수 있게 합니다.

        Args:
            root (Path): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.
            tools (dict[str, Path]): 도구 값을 지정하는 인자입니다.
            kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

        Returns:
            Any: 호출자가 다음 검증 단계에서 사용할 결과 값입니다.
        """
        with patch("problem_studio.core.stress.compile_problem_tools", return_value=tools):
            return stress_test_solutions(root, "alpha", "hidden", **kwargs)

    def test_toy_problem_stress_success(self) -> None:
        """간단한 문제 스트레스 성공 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """비 정답 기대 기대값 허용 정답 상태 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """정답 기대 기대 오답 솔루션 생성 불일치 메타데이터 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """시드 무작위 소스 기반 및 고유 안에서 실행 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """실행 시간 제한 5 분 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """중단 첫 불일치 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """취소 토큰 확인 전에 작업 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """추가 고정 케이스 검증 케이스 및 거부 중복 해시 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """추가 생성기 재현 케이스 검증 케이스 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
