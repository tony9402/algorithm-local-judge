"""Health, readiness, request correlation, and metrics web contracts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from judge.web.app import create_app as create_judge_app
from problem_studio.web.app import create_app as create_studio_app


class WebObservabilityTest(unittest.TestCase):
    def app_clients(self):
        temporary = tempfile.TemporaryDirectory(prefix="alj-observability-")
        studio_workspace = Path(temporary.name) / "studio"
        return temporary, [
            ("judge", TestClient(create_judge_app())),
            ("problem_studio", TestClient(create_studio_app(studio_workspace))),
        ]

    def test_health_and_readiness_for_both_web_apps(self) -> None:
        temporary, clients = self.app_clients()
        with temporary:
            for app_name, client in clients:
                with self.subTest(app=app_name):
                    health = client.get("/healthz")
                    self.assertEqual(health.status_code, 200)
                    self.assertEqual(health.json(), {"status": "ok", "app": app_name})
                    ready = client.get("/readyz")
                    self.assertEqual(ready.status_code, 200)
                    self.assertEqual(ready.json()["checks"]["jobs"], "ok")
                    self.assertEqual(ready.json()["checks"]["static"], "ok")
                    if app_name == "problem_studio":
                        self.assertEqual(ready.json()["checks"]["workspace"], "ok")

    def test_request_id_is_validated_and_security_headers_are_set(self) -> None:
        client = TestClient(create_judge_app())
        accepted = client.get("/healthz", headers={"X-Request-ID": "request-12345678"})
        self.assertEqual(accepted.headers["X-Request-ID"], "request-12345678")
        replaced = client.get("/healthz", headers={"X-Request-ID": "bad value"})
        self.assertRegex(replaced.headers["X-Request-ID"], r"^[0-9a-f]{32}$")
        self.assertEqual(replaced.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(replaced.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(replaced.headers["X-Frame-Options"], "DENY")

    def test_metrics_use_bounded_method_and_status_labels(self) -> None:
        client = TestClient(create_judge_app())
        client.get("/healthz")
        metrics = client.get("/metrics")
        self.assertEqual(metrics.status_code, 200)
        self.assertIn(
            'alj_judge_http_requests_total{method="GET",status="200"}',
            metrics.text,
        )
        self.assertIn("alj_judge_http_request_duration_seconds_sum", metrics.text)
        self.assertIn('alj_judge_jobs{state="queued"} 0', metrics.text)
        self.assertIn('alj_judge_jobs{state="running"} 0', metrics.text)
        self.assertNotIn("/healthz", metrics.text)


if __name__ == "__main__":
    unittest.main()
