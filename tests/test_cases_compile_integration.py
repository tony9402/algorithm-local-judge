"""cases.yml 컴파일 실패가 생성과 실행 흐름을 조기에 중단하는지 실제 명령 경계에서 검증하는 테스트 모듈입니다."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from judge.core.errors import JudgeError
from judge.core.generation import generate
from judge.core.submission import run_submission
from tests.fixture_project import copy_problem_fixture

ROOT = Path(__file__).resolve().parents[1]


class CasesCompileIntegrationTest(unittest.TestCase):
    """케이스 컴파일 통합 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_generate_stops_before_tool_compile_when_cases_compile_fails(self) -> None:
        """생성 중단 전에 도구 컴파일 케이스 컴파일 실패 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-cases-integration-") as tmp:
            project_root = copy_problem_fixture(Path(tmp) / "project")
            with (
                patch(
                    "judge.core.generation.ensure_cases_compiled",
                    side_effect=JudgeError("cases.yml compile failed"),
                ) as ensure,
                patch("judge.core.generation.compile_problem_tools") as compile_tools,
            ):
                with self.assertRaisesRegex(JudgeError, "cases.yml compile failed"):
                    generate("06", "sample", root=project_root)

        ensure.assert_called_once_with("06", "sample", project_root)
        compile_tools.assert_not_called()

    def test_run_stops_before_submission_compile_when_cases_compile_fails(self) -> None:
        """실행 중단 전에 제출 컴파일 케이스 컴파일 실패 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        source = ROOT / "tests" / "fixtures" / "accepted.py"
        with tempfile.TemporaryDirectory(prefix="alj-cases-integration-") as tmp:
            project_root = copy_problem_fixture(Path(tmp) / "project")
            with (
                patch(
                    "judge.core.submission.ensure_cases_compiled",
                    side_effect=JudgeError("cases.yml compile failed"),
                ) as ensure,
                patch("judge.core.submission.prepare_user_submission") as prepare_submission,
            ):
                with self.assertRaisesRegex(JudgeError, "cases.yml compile failed"):
                    run_submission(source, "06", "sample", root=project_root)

        ensure.assert_called_once_with("06", "sample", project_root)
        prepare_submission.assert_not_called()


if __name__ == "__main__":
    unittest.main()
