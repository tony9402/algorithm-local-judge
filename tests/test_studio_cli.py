"""통합 Studio CLI와 기존 호환 진입점 계약을 검증합니다."""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

from alj_launcher import __main__ as standalone_entrypoint
from judge import __version__
from judge.cli import build_parser, normalize_argv
from judge.cli import main as judge_main
from judge.commands import studio
from problem_studio.cli import build_parser as build_problem_studio_parser
from problem_studio.cli import main as problem_studio_main


class StudioCliTest(unittest.TestCase):
    """새 Judge 명령과 기존 실행 파일이 같은 Studio 런타임 계약을 지키는지 확인합니다."""

    def test_judge_studio_parser_accepts_problem_studio_web_options(self) -> None:
        args = build_parser().parse_args(
            normalize_argv(
                [
                    "studio",
                    "--workspace",
                    "workspace",
                    "--clone",
                    "owner/repository",
                    "--branch",
                    "next",
                    "--repo-name",
                    "local",
                    "--host",
                    "localhost",
                    "--port",
                    "9000",
                    "--no-open",
                ]
            )
        )

        self.assertEqual(args.command, "studio")
        self.assertEqual(args.workspace, "workspace")
        self.assertEqual(args.clone, "owner/repository")
        self.assertEqual(args.branch, "next")
        self.assertEqual(args.repo_name, "local")
        self.assertEqual(args.host, "localhost")
        self.assertEqual(args.port, 9000)
        self.assertFalse(args.open)

    def test_judge_studio_uses_compatibility_executable(self) -> None:
        args = argparse.Namespace(
            workspace="workspace",
            clone=None,
            branch=None,
            repo=None,
            repo_name=None,
            host="127.0.0.1",
            port=8775,
            open=False,
        )
        completed = mock.Mock(returncode=17)
        with (
            mock.patch.object(
                studio, "resolve_studio_executable", return_value=Path("/opt/alj/problem-studio")
            ),
            mock.patch.object(studio.subprocess, "run", return_value=completed) as run,
        ):
            result = studio.handle(args)

        self.assertEqual(result, 17)
        run.assert_called_once_with(
            [
                "/opt/alj/problem-studio",
                "web",
                "--workspace",
                "workspace",
                "--host",
                "127.0.0.1",
                "--port",
                "8775",
                "--no-open",
            ],
            check=False,
        )

    def test_both_studio_entrypoints_share_web_option_defaults(self) -> None:
        judge_args = build_parser().parse_args(["studio"])
        legacy_args = build_problem_studio_parser().parse_args(["web"])

        for name in [
            "workspace",
            "clone",
            "branch",
            "repo",
            "repo_name",
            "host",
            "port",
            "open",
        ]:
            self.assertEqual(getattr(judge_args, name), getattr(legacy_args, name))

    def test_cli_versions_use_the_shared_package_version(self) -> None:
        for cli_main in [judge_main, problem_studio_main]:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["--version"])
            self.assertEqual(raised.exception.code, 0)
            self.assertIn(__version__, output.getvalue())

    def test_standalone_problem_studio_filename_keeps_legacy_entrypoint(self) -> None:
        with (
            mock.patch.object(sys, "argv", ["/opt/alj/bin/problem-studio", "--version"]),
            mock.patch.object(standalone_entrypoint, "problem_studio_main", return_value=23),
            mock.patch.object(standalone_entrypoint, "judge_main", return_value=29),
        ):
            result = standalone_entrypoint.main()

        self.assertEqual(result, 23)


if __name__ == "__main__":
    unittest.main()
