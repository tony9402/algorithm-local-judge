"""judge 명령줄 파서와 작은 유틸리티가 명령 정규화, 안전 식별자, 플랫폼 식별자 계약을 지키는지 검증하는 모듈입니다."""

from __future__ import annotations

import contextlib
import io
import unittest

from judge.cli import COMMAND_HANDLERS, build_parser, normalize_argv
from judge.core.errors import JudgeError
from judge.core.paths import normalized_arch, normalized_os, validate_safe_id
from judge.utils.text import format_size


class JudgeStructureTest(unittest.TestCase):
    """채점기 구조 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_normalize_argv_keeps_explicit_command(self) -> None:
        """명령 인자 정규화 명령 인자 유지 명시적 명령 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        self.assertEqual(
            normalize_argv(["run", "--problem", "06", "main.cpp"]),
            ["run", "--problem", "06", "main.cpp"],
        )

    def test_normalize_argv_inserts_default_run_command_after_global_options(self) -> None:
        """명령 인자 정규화 명령 인자 삽입 기본 실행 명령 이후 전역 옵션 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        self.assertEqual(
            normalize_argv(["--profile", "sample", "main.cpp"]),
            ["--profile", "sample", "run", "main.cpp"],
        )

    def test_normalize_argv_supports_equals_form_for_implicit_run(self) -> None:
        """명령 인자 정규화 명령 인자 지원 등호 형식 암시적 실행 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        self.assertEqual(
            normalize_argv(["--problem=06", "--profile=sample", "main.cpp"]),
            ["--problem=06", "--profile=sample", "run", "main.cpp"],
        )

    def test_normalize_argv_inserts_run_before_end_of_options_marker(self) -> None:
        """명령 인자 정규화 명령 인자 삽입 실행 전에 끝 옵션 표식 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        self.assertEqual(
            normalize_argv(["--profile", "sample", "--", "-main.cpp"]),
            ["--profile", "sample", "run", "--", "-main.cpp"],
        )

    def test_normalize_argv_rejects_run_globals_before_non_run_command(self) -> None:
        """명령 인자 정규화 명령 인자 거부 실행 전역 옵션 전에 비 실행 명령 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with self.assertRaises(JudgeError):
            normalize_argv(["--profile", "sample", "generate", "06"])
        with self.assertRaises(JudgeError):
            normalize_argv(["--problem", "06", "cache", "clear", "--dry-run"])

    def test_normalize_argv_keeps_typo_command_as_implicit_run_path(self) -> None:
        """명령 인자 정규화 명령 인자 유지 오타 명령 암시적 실행 경로 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        self.assertEqual(
            normalize_argv(["genrate"]),
            ["run", "genrate"],
        )

    def test_parser_disables_long_option_abbreviation(self) -> None:
        """파서 비활성화 긴 옵션 축약 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(normalize_argv(["--prof", "sample", "main.cpp"]))

    def test_command_registry_matches_parser_choices(self) -> None:
        """명령 레지스트리 일치 파서 선택지 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        parser = build_parser()
        subparsers_action = next(action for action in parser._actions if action.dest == "command")
        self.assertEqual(set(subparsers_action.choices), set(COMMAND_HANDLERS))

    def test_problem_install_parser_accepts_github_source(self) -> None:
        """문제 설치 파서 허용 GitHub 소스 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        parser = build_parser()
        args = parser.parse_args(
            normalize_argv(
                [
                    "problem",
                    "install",
                    "tony9402/algorithm-package",
                    "--asset",
                    "basic-1-macos-arm64.aljpack",
                    "--ref",
                    "main",
                ]
            )
        )

        self.assertEqual(args.command, "problem")
        self.assertEqual(args.problem_command, "install")
        self.assertEqual(args.source, "tony9402/algorithm-package")
        self.assertEqual(args.asset, "basic-1-macos-arm64.aljpack")
        self.assertEqual(args.ref, "main")

    def test_pack_trust_parser_accepts_repository_management(self) -> None:
        """패키지 신뢰 파서 허용 저장소 관리 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        parser = build_parser()
        args = parser.parse_args(normalize_argv(["pack", "trust", "add", "example/problems"]))

        self.assertEqual(args.command, "pack")
        self.assertEqual(args.pack_command, "trust")
        self.assertEqual(args.trust_command, "add")
        self.assertEqual(args.repository, "example/problems")

    def test_web_parser_opens_browser_by_default(self) -> None:
        """웹 파서 열기 브라우저 기본 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        parser = build_parser()

        self.assertTrue(parser.parse_args(normalize_argv(["web"])).open)
        self.assertTrue(parser.parse_args(normalize_argv(["web", "--open"])).open)
        self.assertFalse(parser.parse_args(normalize_argv(["web", "--no-open"])).open)

    def test_web_parser_accepts_background_lifecycle_actions(self) -> None:
        parser = build_parser()

        for action in ("start", "stop", "restart"):
            args = parser.parse_args(normalize_argv(["web", action]))
            self.assertEqual(args.web_action, action)

    def test_validate_safe_id_rejects_path_escape(self) -> None:
        """검증 안전 식별자 거부 경로 경로 이탈 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with self.assertRaises(JudgeError):
            validate_safe_id("problem id", "../06")

    def test_format_size_uses_binary_units(self) -> None:
        """형식 크기 사용 이진 단위 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        self.assertEqual(format_size(1536), "1.5 KiB")

    def test_platform_ids_are_normalized_for_release_artifacts(self) -> None:
        """플랫폼 식별자 정규화 릴리스 산출물 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        self.assertEqual(normalized_os("Darwin"), "macos")
        self.assertEqual(normalized_os("Windows"), "windows")
        self.assertEqual(normalized_arch("x86_64"), "amd64")
        self.assertEqual(normalized_arch("AMD64"), "amd64")
        self.assertEqual(normalized_arch("aarch64"), "arm64")


if __name__ == "__main__":
    unittest.main()
