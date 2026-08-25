"""Judge와 Problem Studio 백그라운드 web 프로세스의 실제 생명주기를 검증합니다."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def health_payload(port: int) -> dict | None:
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/healthz", timeout=0.5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return None


class WebServiceLifecycleE2ETest(unittest.TestCase):
    """설치된 CLI와 같은 subprocess 경로로 start/restart/stop을 실행합니다."""

    def make_environment(self, root: Path) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "ALJ_DATA_HOME": str(root / "data"),
                "ALJ_CACHE_HOME": str(root / "cache"),
                "ALJ_PACK_HOME": str(root / "packs"),
                "ALJ_SOURCE_HOME": str(root / "sources"),
            }
        )
        return environment

    def run_cli(
        self,
        module: str,
        arguments: list[str],
        environment: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", module, *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )

    def wait_for_health(self, port: int, app: str | None, timeout: float = 10) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            payload = health_payload(port)
            if app is None and payload is None:
                return
            if app is not None and payload and payload.get("app") == app:
                return
            time.sleep(0.1)
        self.fail(f"health state did not become {app!r} on port {port}")

    def state(self, root: Path, service: str) -> dict:
        path = root / "data" / "services" / f"{service}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @contextmanager
    def managed_service(
        self,
        module: str,
        prefix: str,
    ) -> Iterator[tuple[Path, dict[str, str]]]:
        with tempfile.TemporaryDirectory(prefix=prefix) as tmp:
            root = Path(tmp)
            environment = self.make_environment(root)
            try:
                yield root, environment
            finally:
                self.run_cli(module, ["web", "stop"], environment)

    def test_judge_web_background_start_restart_and_stop(self) -> None:
        with self.managed_service("judge", "alj-judge-web-service-") as (root, environment):
            port = free_port()

            started = self.run_cli(
                "judge",
                ["web", "start", "--port", str(port), "--no-open"],
                environment,
            )
            self.assertEqual(started.returncode, 0, started.stderr + started.stdout)
            self.assertIn("백그라운드에서 시작", started.stdout)
            self.wait_for_health(port, "judge")
            first_pid = self.state(root, "judge-web")["pid"]

            duplicate = self.run_cli(
                "judge",
                ["web", "start", "--port", str(port), "--no-open"],
                environment,
            )
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("이미 실행 중", duplicate.stderr)

            restarted = self.run_cli(
                "judge",
                ["web", "restart", "--no-open"],
                environment,
            )
            self.assertEqual(restarted.returncode, 0, restarted.stderr + restarted.stdout)
            self.wait_for_health(port, "judge")
            restarted_state = self.state(root, "judge-web")
            self.assertEqual(restarted_state["port"], port)
            self.assertNotEqual(restarted_state["pid"], first_pid)

            stopped = self.run_cli("judge", ["web", "stop"], environment)
            self.assertEqual(stopped.returncode, 0, stopped.stderr + stopped.stdout)
            self.assertIn("종료했습니다", stopped.stdout)
            self.wait_for_health(port, None)
            self.assertFalse((root / "data" / "services" / "judge-web.json").exists())

    def test_problem_studio_web_background_start_restart_and_stop(self) -> None:
        with self.managed_service("problem_studio", "alj-studio-web-service-") as (
            root,
            environment,
        ):
            workspace = root / "workspace"
            workspace.mkdir()
            port = free_port()

            started = self.run_cli(
                "problem_studio",
                [
                    "web",
                    "start",
                    "--workspace",
                    str(workspace),
                    "--port",
                    str(port),
                    "--no-open",
                ],
                environment,
            )
            self.assertEqual(started.returncode, 0, started.stderr + started.stdout)
            self.wait_for_health(port, "problem_studio")
            first_state = self.state(root, "problem-studio-web")
            self.assertIn(str(workspace.resolve()), first_state["childArgs"])

            restarted = self.run_cli(
                "problem_studio",
                ["web", "restart", "--no-open"],
                environment,
            )
            self.assertEqual(restarted.returncode, 0, restarted.stderr + restarted.stdout)
            self.wait_for_health(port, "problem_studio")
            restarted_state = self.state(root, "problem-studio-web")
            self.assertEqual(restarted_state["port"], port)
            self.assertIn(str(workspace.resolve()), restarted_state["childArgs"])
            self.assertNotEqual(restarted_state["pid"], first_state["pid"])

            stopped = self.run_cli("problem_studio", ["web", "stop"], environment)
            self.assertEqual(stopped.returncode, 0, stopped.stderr + stopped.stdout)
            self.wait_for_health(port, None)


if __name__ == "__main__":
    unittest.main()
