from __future__ import annotations

import contextlib
import io
import unittest

from judge.cli import COMMAND_HANDLERS, build_parser, normalize_argv
from judge.core.errors import JudgeError
from judge.core.paths import normalized_arch, normalized_os, validate_safe_id
from judge.utils.text import format_size


class JudgeStructureTest(unittest.TestCase):
    """Focused tests for CLI parsing helpers and small utilities."""

    def test_normalize_argv_keeps_explicit_command(self) -> None:
        """Explicit commands should not be rewritten by the normalizer."""
        self.assertEqual(
            normalize_argv(["run", "--problem", "06", "main.cpp"]),
            ["run", "--problem", "06", "main.cpp"],
        )

    def test_normalize_argv_inserts_default_run_command_after_global_options(self) -> None:
        """Implicit run should be inserted after run-global options."""
        self.assertEqual(
            normalize_argv(["--profile", "sample", "main.cpp"]),
            ["--profile", "sample", "run", "main.cpp"],
        )

    def test_normalize_argv_supports_equals_form_for_implicit_run(self) -> None:
        """Equals-form global options should work with implicit run."""
        self.assertEqual(
            normalize_argv(["--problem=06", "--profile=sample", "main.cpp"]),
            ["--problem=06", "--profile=sample", "run", "main.cpp"],
        )

    def test_normalize_argv_inserts_run_before_end_of_options_marker(self) -> None:
        """The normalizer should preserve `--` for dash-prefixed paths."""
        self.assertEqual(
            normalize_argv(["--profile", "sample", "--", "-main.cpp"]),
            ["--profile", "sample", "run", "--", "-main.cpp"],
        )

    def test_normalize_argv_rejects_run_globals_before_non_run_command(self) -> None:
        """Run-global options before non-run commands should fail clearly."""
        with self.assertRaises(JudgeError):
            normalize_argv(["--profile", "sample", "generate", "06"])
        with self.assertRaises(JudgeError):
            normalize_argv(["--problem", "06", "cache", "clear", "--dry-run"])

    def test_normalize_argv_keeps_typo_command_as_implicit_run_path(self) -> None:
        """Unknown first positionals remain implicit run paths for now."""
        self.assertEqual(
            normalize_argv(["genrate"]),
            ["run", "genrate"],
        )

    def test_parser_disables_long_option_abbreviation(self) -> None:
        """The parser should reject abbreviated long options."""
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(normalize_argv(["--prof", "sample", "main.cpp"]))

    def test_command_registry_matches_parser_choices(self) -> None:
        """Parser subcommands should stay in sync with command handlers."""
        parser = build_parser()
        subparsers_action = next(action for action in parser._actions if action.dest == "command")
        self.assertEqual(set(subparsers_action.choices), set(COMMAND_HANDLERS))

    def test_problem_install_parser_accepts_github_source(self) -> None:
        """The easy problem installer should accept repository and asset inputs."""
        parser = build_parser()
        args = parser.parse_args(
            normalize_argv(
                [
                    "problem",
                    "install",
                    "tony9402/algorithm-modules",
                    "--asset",
                    "basic-1-macos-arm64.aljpack",
                ]
            )
        )

        self.assertEqual(args.command, "problem")
        self.assertEqual(args.problem_command, "install")
        self.assertEqual(args.source, "tony9402/algorithm-modules")
        self.assertEqual(args.asset, "basic-1-macos-arm64.aljpack")

    def test_web_parser_opens_browser_by_default(self) -> None:
        """`judge web` should open the browser unless explicitly disabled."""
        parser = build_parser()

        self.assertTrue(parser.parse_args(normalize_argv(["web"])).open)
        self.assertTrue(parser.parse_args(normalize_argv(["web", "--open"])).open)
        self.assertFalse(parser.parse_args(normalize_argv(["web", "--no-open"])).open)

    def test_validate_safe_id_rejects_path_escape(self) -> None:
        """Safe id validation should reject path traversal tokens."""
        with self.assertRaises(JudgeError):
            validate_safe_id("problem id", "../06")

    def test_format_size_uses_binary_units(self) -> None:
        """Byte formatting should use binary units."""
        self.assertEqual(format_size(1536), "1.5 KiB")

    def test_platform_ids_are_normalized_for_release_artifacts(self) -> None:
        """OS and architecture names should match release artifact ids."""
        self.assertEqual(normalized_os("Darwin"), "macos")
        self.assertEqual(normalized_os("Windows"), "windows")
        self.assertEqual(normalized_arch("x86_64"), "amd64")
        self.assertEqual(normalized_arch("AMD64"), "amd64")
        self.assertEqual(normalized_arch("aarch64"), "arm64")


if __name__ == "__main__":
    unittest.main()
