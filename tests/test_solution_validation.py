"""솔루션 기대 결과 추론과 문제 솔루션 검증 결과 집계 계약을 검증하는 테스트 모듈입니다."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from judge.core.errors import JudgeError
from judge.core.solution_validation import (
    discover_solution_expectations,
    effective_solution_status,
    expected_status_from_solution_name,
    verify_problem_solutions,
)
from judge.utils.fs import write_json


def create_problem(root: Path) -> Path:
    """문제 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        root (Path): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.

    Returns:
        Path: 솔루션 검증 테스트에 사용할 최소 문제 디렉터리 경로입니다.
    """
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
    """솔루션 검증 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_expected_status_from_solution_name(self) -> None:
        """기대 상태 솔루션 이름 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        self.assertEqual(
            expected_status_from_solution_name(Path("slow_solution.pypy.tle.py")),
            ("tle", "time_limit"),
        )
        with self.assertRaisesRegex(JudgeError, "expected result token"):
            expected_status_from_solution_name(Path("helper.cpp"))

    def test_discover_solution_expectations_requires_tokens(self) -> None:
        """탐색 솔루션 기대 결과 요구 토큰 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-test-") as tmp:
            problem = Path(tmp) / "problem"
            solutions = problem / "solutions"
            solutions.mkdir(parents=True)
            (solutions / "main_solution.ac.cpp").write_text("", encoding="utf-8")
            (solutions / "helper.cpp").write_text("", encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "expected result token"):
                discover_solution_expectations(problem)

    def test_pypy_solution_expectation_uses_pypy_runtime(self) -> None:
        """Problem Studio PyPy 솔루션 파일명이 기대 토큰과 실행 언어를 모두 보존하는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-pypy-test-") as tmp:
            root = Path(tmp)
            problem = create_problem(root)
            pypy_solution = problem / "solutions" / "pypy_solution.pypy.ac.py"
            pypy_solution.write_text("print(1)\n", encoding="utf-8")
            expectations = discover_solution_expectations(problem)
            pypy_expectation = next(item for item in expectations if item.path == pypy_solution)
            self.assertEqual(pypy_expectation.status, "accepted")
            self.assertEqual(pypy_expectation.language, "pypy")
            run_root = root / "runs"

            def fake_run_submission(
                source: Path,
                problem_id: str | None = None,
                profile: str | None = None,
                **kwargs,
            ) -> Path:
                self.assertEqual(source, pypy_solution)
                self.assertEqual(kwargs.get("language"), "pypy")
                run_dir = run_root / "pypy-run"
                write_json(
                    run_dir / "result.json",
                    {
                        "runId": "pypy-run",
                        "problemId": problem_id,
                        "profile": profile,
                        "language": "pypy",
                        "status": "accepted",
                        "cases": [{"case": "001", "status": "ok"}],
                        "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
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
                result = verify_problem_solutions(
                    "01",
                    "hidden",
                    root,
                    raise_on_failure=False,
                    solution_paths=["solutions/pypy_solution.pypy.ac.py"],
                )

        payload = result.to_dict(root)
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["checks"][0]["language"], "pypy")

    def test_verify_problem_solutions_passes_matching_results(self) -> None:
        """검증 문제 솔루션 통과 일치 결과 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
                """실제 채점 실행을 대체해 웹 API와 솔루션 검증 테스트가 고정된 실행 결과를 받게 합니다.

                Args:
                    source (Path): 분석하거나 실행할 소스 코드 문자열입니다.
                    problem_id (str | None): 테스트가 생성하거나 조회할 문제 식별자입니다.
                    profile (str | None): 검증이나 실행에 사용할 테스트 프로필 이름입니다.
                    root (Path | None): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.
                    stop_on_first_failure (bool): 첫 실패에서 검증을 중단해야 하는지 나타내는 플래그입니다.

                Returns:
                    Path: 테스트가 생성하거나 조회한 파일 시스템 경로입니다.
                """
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
        """검증 문제 솔루션 보고 불일치 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
                """실제 채점 실행을 대체해 웹 API와 솔루션 검증 테스트가 고정된 실행 결과를 받게 합니다.

                Args:
                    source (Path): 분석하거나 실행할 소스 코드 문자열입니다.
                    problem_id (str | None): 테스트가 생성하거나 조회할 문제 식별자입니다.
                    profile (str | None): 검증이나 실행에 사용할 테스트 프로필 이름입니다.
                    root (Path | None): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.
                    stop_on_first_failure (bool): 첫 실패에서 검증을 중단해야 하는지 나타내는 플래그입니다.

                Returns:
                    Path: 테스트가 생성하거나 조회한 파일 시스템 경로입니다.
                """
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
        """검증 문제 솔루션 가능 반환 불일치 페이로드 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
                """실제 채점 실행을 대체해 웹 API와 솔루션 검증 테스트가 고정된 실행 결과를 받게 합니다.

                Args:
                    source (Path): 분석하거나 실행할 소스 코드 문자열입니다.
                    problem_id (str | None): 테스트가 생성하거나 조회할 문제 식별자입니다.
                    profile (str | None): 검증이나 실행에 사용할 테스트 프로필 이름입니다.
                    root (Path | None): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.
                    stop_on_first_failure (bool): 첫 실패에서 검증을 중단해야 하는지 나타내는 플래그입니다.

                Returns:
                    Path: 테스트가 생성하거나 조회한 파일 시스템 경로입니다.
                """
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
        """검증 문제 솔루션 가능 한도 하나 솔루션 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
                """실제 채점 실행을 대체해 웹 API와 솔루션 검증 테스트가 고정된 실행 결과를 받게 합니다.

                Args:
                    source (Path): 분석하거나 실행할 소스 코드 문자열입니다.
                    problem_id (str | None): 테스트가 생성하거나 조회할 문제 식별자입니다.
                    profile (str | None): 검증이나 실행에 사용할 테스트 프로필 이름입니다.
                    root (Path | None): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.
                    stop_on_first_failure (bool): 첫 실패에서 검증을 중단해야 하는지 나타내는 플래그입니다.

                Returns:
                    Path: 테스트가 생성하거나 조회한 파일 시스템 경로입니다.
                """
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

    def test_effective_solution_status_promotes_wa_to_tle_when_any_case_times_out(self) -> None:
        """TLE 기대 솔루션은 WA 케이스가 있어도 TLE 케이스가 있으면 TLE로 집계되어야 합니다."""
        status, evidence = effective_solution_status(
            "wrong_answer",
            [
                {"case": "001", "status": "wrong_answer"},
                {"case": "002", "status": "time_limit"},
            ],
        )

        self.assertEqual(status, "time_limit")
        self.assertEqual(evidence["caseStatusCounts"]["wrong_answer"], 1)
        self.assertEqual(evidence["caseStatusCounts"]["time_limit"], 1)
        self.assertEqual(evidence["rankedStatus"], "time_limit")

    def test_verify_problem_solutions_accepts_tle_expected_with_mixed_wa_and_tle(self) -> None:
        """TLE 예상 솔루션의 WA+TLE 혼합 케이스가 기대 결과와 일치하는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-test-") as tmp:
            root = Path(tmp)
            problem = create_problem(root)
            slow = problem / "solutions" / "slow_solution.tle.cpp"
            slow.write_text("// slow\n", encoding="utf-8")
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
                        "status": "wrong_answer",
                        "cases": [
                            {"case": "001", "status": "wrong_answer"},
                            {"case": "002", "status": "time_limit"},
                        ],
                        "metrics": {"maxTimeMs": 2000, "maxMemoryBytes": 1024},
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
                result = verify_problem_solutions(
                    "01",
                    "hidden",
                    root,
                    raise_on_failure=False,
                    solution_paths=["solutions/slow_solution.tle.cpp"],
                )

        payload = result.to_dict(root)
        self.assertTrue(payload["passed"])
        check = payload["checks"][0]
        self.assertEqual(check["expectedStatus"], "time_limit")
        self.assertEqual(check["actualStatus"], "time_limit")
        self.assertEqual(check["rawActualStatus"], "wrong_answer")
        self.assertTrue(check["passed"])

    def test_verify_problem_solutions_rejects_wa_expected_when_any_case_times_out(self) -> None:
        """WA 예상 솔루션에 TLE 케이스가 포함되면 TLE로 집계되어 불일치해야 합니다."""
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
                        "language": "python",
                        "status": "wrong_answer",
                        "cases": [
                            {"case": "001", "status": "wrong_answer"},
                            {"case": "002", "status": "time_limit"},
                        ],
                        "metrics": {"maxTimeMs": 2000, "maxMemoryBytes": 1024},
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
                result = verify_problem_solutions(
                    "01",
                    "hidden",
                    root,
                    raise_on_failure=False,
                    solution_paths=["solutions/wrong_solution.wa.py"],
                )

        payload = result.to_dict(root)
        self.assertFalse(payload["passed"])
        check = payload["checks"][0]
        self.assertEqual(check["expectedStatus"], "wrong_answer")
        self.assertEqual(check["actualStatus"], "time_limit")
        self.assertEqual(check["rawActualStatus"], "wrong_answer")

    def test_verify_problem_solutions_reports_each_completed_check(self) -> None:
        """전체 검증 중 솔루션 하나가 끝날 때마다 부분 결과 콜백이 호출되어야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-test-") as tmp:
            root = Path(tmp)
            create_problem(root)
            run_root = root / "runs"
            completed = []

            def fake_run_submission(
                source: Path,
                problem_id: str | None = None,
                profile: str | None = None,
                root: Path | None = None,
                stop_on_first_failure: bool = True,
            ) -> Path:
                run_dir = run_root / source.stem
                status = "wrong_answer" if ".wa." in source.name else "accepted"
                case_status = "wrong_answer" if status == "wrong_answer" else "ok"
                write_json(
                    run_dir / "result.json",
                    {
                        "runId": source.stem,
                        "problemId": problem_id,
                        "profile": profile,
                        "language": "python" if source.suffix == ".py" else "cpp",
                        "status": status,
                        "cases": [{"case": "001", "status": case_status}],
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
                result = verify_problem_solutions(
                    "01",
                    "hidden",
                    root,
                    raise_on_failure=False,
                    on_check=lambda check, index, total: completed.append(
                        (check.source.name, index, total, check.passed)
                    ),
                )

        self.assertTrue(result.passed)
        self.assertEqual(len(completed), 2)
        self.assertEqual(completed[0][1:], (1, 2, True))
        self.assertEqual(completed[1][1:], (2, 2, True))

    def test_verify_problem_solutions_can_run_solutions_in_parallel(self) -> None:
        """max_workers가 2 이상이면 솔루션 검증이 병렬 실행되고 최종 결과는 안정적으로 정렬됩니다."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-test-") as tmp:
            root = Path(tmp)
            create_problem(root)
            run_root = root / "runs"
            main_started = threading.Event()
            wrong_started = threading.Event()

            def fake_run_submission(
                source: Path,
                problem_id: str | None = None,
                profile: str | None = None,
                root: Path | None = None,
                stop_on_first_failure: bool = True,
                **kwargs,
            ) -> Path:
                if source.name == "main_solution.ac.cpp":
                    main_started.set()
                    self.assertTrue(wrong_started.wait(2), "wrong solution did not start")
                if source.name == "wrong_solution.wa.py":
                    wrong_started.set()
                    self.assertTrue(main_started.wait(2), "main solution did not start")
                self.assertIn("prepared_tools", kwargs)
                self.assertIn("prepared_data_dirs", kwargs)
                run_dir = run_root / source.stem
                status = "wrong_answer" if ".wa." in source.name else "accepted"
                case_status = "wrong_answer" if status == "wrong_answer" else "ok"
                write_json(
                    run_dir / "result.json",
                    {
                        "runId": source.stem,
                        "problemId": problem_id,
                        "profile": profile,
                        "language": "python" if source.suffix == ".py" else "cpp",
                        "status": status,
                        "cases": [{"case": "001", "status": case_status}],
                        "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1},
                    },
                )
                return run_dir

            with (
                patch("judge.core.solution_validation.generate", return_value=root / "cache"),
                patch(
                    "judge.core.solution_validation.compile_problem_tools",
                    return_value={"checker": root / "checker"},
                ) as mocked_tools,
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
                    max_workers=2,
                )

        self.assertTrue(result.passed)
        self.assertEqual(mocked_tools.call_count, 1)
        self.assertEqual(mocked_run.call_count, 2)
        self.assertEqual(
            [check.source.name for check in result.checks],
            [
                "main_solution.ac.cpp",
                "wrong_solution.wa.py",
            ],
        )

    def test_parallel_solution_verification_stops_submitting_after_cancel(self) -> None:
        """병렬 검증 취소 후에는 아직 제출하지 않은 솔루션 작업을 새로 시작하지 않아야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-solution-test-") as tmp:
            root = Path(tmp)
            problem = create_problem(root)
            for index in range(4):
                (problem / "solutions" / f"extra_{index}.ac.cpp").write_text(
                    "// extra\n",
                    encoding="utf-8",
                )
            run_root = root / "runs"
            cancel_requested = threading.Event()
            started: list[str] = []
            started_lock = threading.Lock()

            def fake_run_submission(
                source: Path,
                problem_id: str | None = None,
                profile: str | None = None,
                root: Path | None = None,
                stop_on_first_failure: bool = True,
                **kwargs,
            ) -> Path:
                with started_lock:
                    started.append(source.name)
                run_dir = run_root / source.stem
                status = "wrong_answer" if ".wa." in source.name else "accepted"
                case_status = "wrong_answer" if status == "wrong_answer" else "ok"
                write_json(
                    run_dir / "result.json",
                    {
                        "runId": source.stem,
                        "problemId": problem_id,
                        "profile": profile,
                        "language": "cpp",
                        "status": status,
                        "cases": [{"case": "001", "status": case_status}],
                        "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1},
                    },
                )
                return run_dir

            def on_check(*_args) -> None:
                cancel_requested.set()

            def cancel_check() -> None:
                if cancel_requested.is_set():
                    raise RuntimeError("cancelled")

            with (
                patch("judge.core.solution_validation.generate", return_value=root / "cache"),
                patch(
                    "judge.core.solution_validation.compile_problem_tools",
                    return_value={"checker": root / "checker"},
                ),
                patch(
                    "judge.core.solution_validation.run_submission",
                    side_effect=fake_run_submission,
                ),
                self.assertRaisesRegex(RuntimeError, "cancelled"),
            ):
                verify_problem_solutions(
                    "01",
                    "hidden",
                    root,
                    raise_on_failure=False,
                    max_workers=2,
                    on_check=on_check,
                    cancel_check=cancel_check,
                )

        self.assertLessEqual(len(started), 2)


if __name__ == "__main__":
    unittest.main()
