"""Docker 진단, sandbox preflight, 안전한 웹 기본값의 회귀 테스트입니다."""

from __future__ import annotations

import io
import os
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from judge.commands.doctor import collect_diagnostics, print_text_report
from judge.core.docker_runtime import (
    SANDBOX_MODE_ENV,
    collect_docker_diagnostics,
    docker_install_hint,
    ensure_sandbox_preflight,
    sandbox_mode,
)
from judge.core.errors import JudgeError
from judge.web.server import run_server

ROOT = Path(__file__).resolve().parents[1]


def missing_docker_diagnostics() -> dict[str, object]:
    return {
        "label": "Docker runtime",
        "status": "missing",
        "path": None,
        "env": None,
        "configured": None,
        "candidates": ["docker"],
        "cliStatus": "missing",
        "daemonStatus": "not_checked",
        "serverVersion": None,
        "error": "Docker CLI was not found on PATH.",
        "installHint": docker_install_hint("Darwin"),
        "sandboxReady": False,
    }


class DockerDiagnosticsTest(unittest.TestCase):
    def test_missing_cli_has_platform_specific_install_guidance(self) -> None:
        with (
            patch("judge.core.docker_runtime.shutil.which", return_value=None),
            patch("judge.core.docker_runtime.platform.system", return_value="Darwin"),
        ):
            diagnostics = collect_docker_diagnostics()

        self.assertEqual(diagnostics["status"], "missing")
        self.assertEqual(diagnostics["daemonStatus"], "not_checked")
        self.assertFalse(diagnostics["sandboxReady"])
        self.assertIn("Docker Desktop for Mac", diagnostics["installHint"])
        self.assertIn(
            "docs.docker.com/desktop/setup/install/mac-install", diagnostics["installHint"]
        )
        self.assertIn("Docker Engine", docker_install_hint("Linux"))
        self.assertIn("docs.docker.com/engine/install", docker_install_hint("Linux"))

    def test_daemon_unavailable_is_distinct_from_missing_cli(self) -> None:
        result = subprocess.CompletedProcess(
            args=["docker", "info"],
            returncode=1,
            stdout="",
            stderr="Cannot connect to the Docker daemon",
        )
        with (
            patch("judge.core.docker_runtime.shutil.which", return_value="/usr/bin/docker"),
            patch("judge.core.docker_runtime.subprocess.run", return_value=result),
            patch("judge.core.docker_runtime.platform.system", return_value="Linux"),
        ):
            diagnostics = collect_docker_diagnostics()

        self.assertEqual(diagnostics["status"], "unavailable")
        self.assertEqual(diagnostics["cliStatus"], "ok")
        self.assertEqual(diagnostics["daemonStatus"], "unavailable")
        self.assertIn("Cannot connect", diagnostics["error"])
        self.assertIn("systemctl start docker", diagnostics["installHint"])

    def test_running_daemon_reports_server_version(self) -> None:
        result = subprocess.CompletedProcess(
            args=["docker", "info"],
            returncode=0,
            stdout="27.5.1\n",
            stderr="",
        )
        with (
            patch("judge.core.docker_runtime.shutil.which", return_value="/usr/bin/docker"),
            patch("judge.core.docker_runtime.subprocess.run", return_value=result) as run,
        ):
            diagnostics = collect_docker_diagnostics()

        self.assertEqual(diagnostics["status"], "ok")
        self.assertEqual(diagnostics["daemonStatus"], "running")
        self.assertEqual(diagnostics["serverVersion"], "27.5.1")
        self.assertTrue(diagnostics["sandboxReady"])
        self.assertEqual(run.call_args.args[0][1:3], ["info", "--format"])

    def test_daemon_probe_timeout_is_actionable(self) -> None:
        with (
            patch("judge.core.docker_runtime.shutil.which", return_value="/usr/bin/docker"),
            patch(
                "judge.core.docker_runtime.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["docker", "info"], 3),
            ),
            patch("judge.core.docker_runtime.platform.system", return_value="Linux"),
        ):
            diagnostics = collect_docker_diagnostics()

        self.assertEqual(diagnostics["status"], "unavailable")
        self.assertIn("timed out after 3 seconds", diagnostics["error"])
        self.assertIn("systemctl start docker", diagnostics["installHint"])

    def test_explicit_docker_mode_fails_closed_when_docker_is_missing(self) -> None:
        with self.assertRaisesRegex(JudgeError, "fail closed"):
            ensure_sandbox_preflight("docker", diagnostics=missing_docker_diagnostics())

    def test_invalid_sandbox_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(JudgeError, "supported modes"):
            sandbox_mode("auto")


class DockerUserExperienceTest(unittest.TestCase):
    def test_doctor_includes_docker_cli_and_daemon_status(self) -> None:
        docker = missing_docker_diagnostics()
        with (
            patch("judge.commands.doctor.installed_packs", return_value=[]),
            patch(
                "judge.commands.doctor.official_pack_repository",
                return_value="owner/repository",
            ),
            patch("judge.commands.doctor.collect_docker_diagnostics", return_value=docker),
            patch.dict(os.environ, {SANDBOX_MODE_ENV: "off"}),
        ):
            diagnostics = collect_diagnostics()

        output = io.StringIO()
        with redirect_stdout(output):
            print_text_report(diagnostics, verbose=True)

        self.assertEqual(diagnostics["tools"]["docker"], docker)
        self.assertIn("Docker runtime: WARN docker (optional)", output.getvalue())
        self.assertIn("daemon: not_checked", output.getvalue())
        self.assertIn("Docker Desktop for Mac", output.getvalue())

    def test_doctor_marks_missing_docker_required_mode_as_warning(self) -> None:
        with (
            patch("judge.commands.doctor.installed_packs", return_value=[]),
            patch(
                "judge.commands.doctor.official_pack_repository",
                return_value="owner/repository",
            ),
            patch(
                "judge.commands.doctor.collect_docker_diagnostics",
                return_value=missing_docker_diagnostics(),
            ),
            patch.dict(os.environ, {SANDBOX_MODE_ENV: "docker"}),
        ):
            diagnostics = collect_diagnostics()

        self.assertEqual(diagnostics["status"], "warning")
        self.assertTrue(diagnostics["tools"]["docker"]["required"])

    def test_web_default_mode_warns_but_starts(self) -> None:
        app = Mock()
        output = io.StringIO()
        with (
            patch(
                "judge.web.server.ensure_sandbox_preflight",
                return_value=("off", missing_docker_diagnostics()),
            ),
            patch("judge.web.server.create_app", return_value=app),
            patch("judge.web.server.uvicorn.run") as uvicorn_run,
            redirect_stdout(output),
        ):
            run_server("127.0.0.1", 8765)

        uvicorn_run.assert_called_once()
        self.assertIn("Docker runtime preflight: WARN", output.getvalue())
        self.assertIn(f"{SANDBOX_MODE_ENV}=docker", output.getvalue())

    def test_web_explicit_docker_mode_does_not_start_without_daemon(self) -> None:
        with (
            patch.dict(os.environ, {SANDBOX_MODE_ENV: "docker"}),
            patch(
                "judge.core.docker_runtime.collect_docker_diagnostics",
                return_value=missing_docker_diagnostics(),
            ),
            patch("judge.web.server.uvicorn.run") as uvicorn_run,
            self.assertRaisesRegex(JudgeError, "fail closed"),
        ):
            run_server("127.0.0.1", 8765)

        uvicorn_run.assert_not_called()

    def test_container_default_does_not_enable_remote_run(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        command = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))

        self.assertIn('"--host", "0.0.0.0"', command)
        self.assertNotIn("--allow-remote-run", command)


if __name__ == "__main__":
    unittest.main()
