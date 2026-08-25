"""백그라운드 web 서비스 상태 파일과 프로세스 소유권 보호를 검증합니다."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from alj_core.errors import JudgeError
from alj_core.web_service import (
    WebServiceSpec,
    service_state_path,
    start_web_service,
    stop_web_service,
)


class WebServiceSafetyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="alj-web-service-unit-")
        self.addCleanup(self.directory.cleanup)
        self.data_home = Path(self.directory.name) / "data"
        self.environment = patch.dict(os.environ, {"ALJ_DATA_HOME": str(self.data_home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.spec = WebServiceSpec(
            name="test-web",
            display_name="Test web",
            module="judge",
            health_app="judge",
        )

    def write_state(self, **overrides) -> Path:
        state = {
            "schemaVersion": 1,
            "service": self.spec.name,
            "pid": 4242,
            "token": "a" * 32,
            "host": "127.0.0.1",
            "port": 8765,
            "url": "http://127.0.0.1:8765",
            "logPath": str(self.data_home / "logs" / "test-web.log"),
            "childArgs": ["--host", "127.0.0.1", "--port", "8765", "--no-open"],
            "openBrowser": False,
        }
        state.update(overrides)
        path = service_state_path(self.spec)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(state), encoding="utf-8")
        return path

    def test_stop_never_signals_a_pid_with_a_different_service_token(self) -> None:
        state_path = self.write_state()
        with (
            patch("alj_core.web_service._process_is_alive", return_value=True),
            patch("alj_core.web_service._process_matches_state", return_value=False),
            patch("alj_core.web_service.os.kill") as kill,
        ):
            result = stop_web_service(self.spec)

        self.assertEqual(result["status"], "not-running")
        self.assertEqual(result["unrelatedPid"], 4242)
        kill.assert_not_called()
        self.assertFalse(state_path.exists())

    def test_corrupt_state_fails_closed_without_signalling(self) -> None:
        self.write_state(token="invalid")
        with (
            patch("alj_core.web_service.os.kill") as kill,
            self.assertRaisesRegex(JudgeError, "상태 파일이 손상"),
        ):
            stop_web_service(self.spec)

        kill.assert_not_called()

    def test_start_cleans_up_child_when_state_cannot_be_written(self) -> None:
        process = Mock(pid=4343)
        process.poll.return_value = None
        with (
            patch("alj_core.web_service.subprocess.Popen", return_value=process),
            patch(
                "alj_core.web_service._atomic_write_state",
                side_effect=OSError("write failed"),
            ),
            self.assertRaisesRegex(OSError, "write failed"),
        ):
            start_web_service(
                self.spec,
                child_args=["--host", "127.0.0.1", "--port", "8765", "--no-open"],
                host="127.0.0.1",
                port=8765,
                open_browser=False,
            )

        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=2)
        self.assertFalse(service_state_path(self.spec).exists())


if __name__ == "__main__":
    unittest.main()
