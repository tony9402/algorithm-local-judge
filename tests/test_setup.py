"""First-run setup command contracts for a local Judge installation."""

from __future__ import annotations

import argparse
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from judge.cli import main
from judge.commands import setup
from judge.core.errors import JudgeError


def setup_args(**overrides) -> argparse.Namespace:
    values = {
        "repository": "tony9402/algorithm-package",
        "check_only": False,
        "toolchains": "auto",
        "yes": False,
        "no_install_problems": False,
        "no_web": True,
        "no_open": False,
        "port": 8765,
        "verbose": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class SetupCommandTest(unittest.TestCase):
    def test_parser_exposes_noninteractive_check_only_mode(self) -> None:
        with (
            patch("judge.commands.setup.collect_diagnostics", return_value={}),
            patch("judge.commands.setup.print_text_report"),
        ):
            self.assertEqual(main(["setup", "--check-only"]), 0)

    def test_parser_exposes_toolchain_modes(self) -> None:
        with (
            patch("judge.commands.setup.collect_diagnostics", return_value={}),
            patch("judge.commands.setup.print_text_report"),
        ):
            self.assertEqual(main(["setup", "--toolchains", "none", "--check-only"]), 0)

    def test_managed_mode_fails_closed_when_provider_is_unconfigured(self) -> None:
        with patch(
            "judge.commands.setup.managed_provider_status",
            return_value={
                "status": "unconfigured",
                "active": None,
                "error": "managed toolchain provider is not configured",
            },
        ):
            with self.assertRaisesRegex(JudgeError, "provider is not configured"):
                setup.configure_toolchain_mode("managed")

    def test_setup_installs_official_problems_when_empty(self) -> None:
        installed = {
            "installType": "pack",
            "installedPath": "/tmp/basic",
            "label": "basic",
        }
        with (
            patch("judge.commands.setup.collect_diagnostics", return_value={}),
            patch("judge.commands.setup.print_text_report"),
            patch(
                "judge.commands.setup.discover_problem_ids",
                side_effect=[[], ["01", "02"]],
            ),
            patch(
                "judge.commands.setup.install_problem_source", return_value=installed
            ) as install,
            patch("judge.commands.setup.print_installed_problem_source"),
        ):
            self.assertEqual(setup.handle(setup_args()), 0)
        install.assert_called_once_with("tony9402/algorithm-package")

    def test_setup_starts_only_loopback_web_server(self) -> None:
        with (
            patch("judge.commands.setup.collect_diagnostics", return_value={}),
            patch("judge.commands.setup.print_text_report"),
            patch("judge.commands.setup.discover_problem_ids", return_value=["01"]),
            patch("judge.commands.setup.run_server") as run_server,
        ):
            self.assertEqual(
                setup.handle(setup_args(no_web=False, no_open=True, port=9876)),
                0,
            )
        run_server.assert_called_once_with("127.0.0.1", 9876, False, False, False)

    def test_setup_can_skip_problem_install_without_hiding_next_step(self) -> None:
        output = io.StringIO()
        with (
            patch("judge.commands.setup.collect_diagnostics", return_value={}),
            patch("judge.commands.setup.print_text_report"),
            patch("judge.commands.setup.discover_problem_ids", return_value=[]),
            patch("judge.commands.setup.install_problem_source") as install,
            redirect_stdout(output),
        ):
            self.assertEqual(
                setup.handle(setup_args(no_install_problems=True)),
                0,
            )
        install.assert_not_called()
        self.assertIn("judge problem install", output.getvalue())


if __name__ == "__main__":
    unittest.main()
