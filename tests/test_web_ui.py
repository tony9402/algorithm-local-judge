from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from judge.core.errors import JudgeError
from judge.web import services
from judge.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse the small SSE subset emitted by the local web UI."""
    events = []
    for block in text.strip().split("\n\n"):
        event = "message"
        data = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            if line.startswith("data:"):
                data = json.loads(line.removeprefix("data:").strip())
        events.append((event, data))
    return events


class WebUiTest(unittest.TestCase):
    """Smoke tests for the local FastAPI web UI."""

    def test_dashboard_status_endpoint(self) -> None:
        """The dashboard API should expose problems, packs, and cache status."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
                "ALJ_PYTHON": sys.executable,
            }
            with patch.dict(os.environ, env, clear=True):
                client = TestClient(create_app())
                page = client.get("/")
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.headers.get("cache-control"), "no-store")
                self.assertIn("문제 팩 설치", page.text)
                self.assertIn("Cache 정리", page.text)
                self.assertIn("Samples", page.text)
                self.assertIn("themeToggleButton", page.text)
                self.assertIn("sourceLineNumbers", page.text)
                self.assertIn("sourceHighlight", page.text)
                self.assertIn("editor-toolbar", page.text)
                self.assertIn("sourceHistoryList", page.text)
                self.assertIn("sourceReadiness", page.text)
                self.assertIn("Run Hidden Tests", page.text)
                self.assertIn("toastHost", page.text)
                self.assertIn("generationProgress", page.text)
                self.assertNotIn("profileSelect", page.text)
                self.assertNotIn("Refresh</button>", page.text)
                self.assertIn("/static/app.js?v=", page.text)
                app_js = client.get("/static/app.js")
                self.assertEqual(app_js.status_code, 200)
                self.assertEqual(app_js.headers.get("cache-control"), "no-store")
                self.assertIn("function bindEvents", app_js.text)
                self.assertIn("function updateEditorLineNumbers", app_js.text)
                self.assertIn("function highlightCode", app_js.text)
                self.assertIn("function renderSourceHistory", app_js.text)
                self.assertIn("function restoreRunResult", app_js.text)
                self.assertIn('/api/sources', app_js.text)
                self.assertIn('/api/config', app_js.text)
                self.assertNotIn("profileSelect", app_js.text)
                status = client.get("/api/status")
                self.assertEqual(status.status_code, 200)
                data = status.json()
                self.assertIn("problems", data)
                self.assertIn("cache", data)
                self.assertIn("sources", data["cache"])
                self.assertEqual(data["config"]["sampleProfile"], "sample")
                self.assertEqual(data["config"]["judgeProfile"], "hidden")
                self.assertFalse(data["config"]["webDebug"])
                config = client.get("/api/config")
                self.assertEqual(config.status_code, 200)
                self.assertEqual(config.json()["judgeProfile"], "hidden")

    def test_run_pasted_python_submission(self) -> None:
        """Pasted Python source should be judged through the web API."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
                "ALJ_PYTHON": sys.executable,
            }
            source = (ROOT / "tests" / "fixtures" / "accepted.py").read_text(encoding="utf-8")
            with patch.dict(os.environ, env, clear=True):
                client = TestClient(create_app())
                response = client.post(
                    "/api/run",
                    json={
                        "problem_id": "06",
                        "profile": "sample",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": source,
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result["status"], "accepted")
                self.assertEqual(result["profile"], "hidden")
                self.assertEqual(result["language"], "python")
                self.assertIn("maxTimeLabel", result["metrics"])
                self.assertIn("maxMemoryLabel", result["metrics"])
                sources = client.get("/api/sources")
                self.assertEqual(sources.status_code, 200, sources.text)
                source_entry = sources.json()["sources"][0]
                self.assertEqual(source_entry["filename"], "main.py")
                self.assertEqual(source_entry["problemId"], "06")
                self.assertEqual(source_entry["lastRun"]["status"], "accepted")
                self.assertEqual(source_entry["lastRun"]["runId"], result["runId"])
                detail = client.get(f"/api/sources/{source_entry['sourceId']}")
                self.assertEqual(detail.status_code, 200, detail.text)
                self.assertEqual(detail.json()["sourceText"], source)
                self.assertEqual(detail.json()["lastRunResult"]["status"], "accepted")
                self.assertEqual(detail.json()["lastRunResult"]["runId"], result["runId"])
                cleared = client.post(
                    "/api/cache/clear",
                    json={"runs": True, "dry_run": False},
                )
                self.assertEqual(cleared.status_code, 200, cleared.text)
                after_clear = client.get("/api/sources")
                self.assertEqual(after_clear.status_code, 200, after_clear.text)
                self.assertEqual(after_clear.json()["sources"], [])

    def test_cached_source_can_be_deleted_individually(self) -> None:
        """One cached source entry should be removable without clearing every cache."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
                "ALJ_PYTHON": sys.executable,
            }
            with patch.dict(os.environ, env, clear=True):
                source_path = services.save_text_source("print(1)\n", "main.py", "06")
                source_id = source_path.parent.name
                client = TestClient(create_app())
                before = client.get("/api/sources")
                self.assertEqual(before.status_code, 200, before.text)
                self.assertEqual(len(before.json()["sources"]), 1)
                deleted = client.delete(f"/api/sources/{source_id}")
                self.assertEqual(deleted.status_code, 200, deleted.text)
                self.assertTrue(deleted.json()["deleted"])
                after = client.get("/api/sources")
                self.assertEqual(after.status_code, 200, after.text)
                self.assertEqual(after.json()["sources"], [])

    def test_wrong_case_endpoint_truncates_large_artifacts(self) -> None:
        """Large wrong-answer artifacts should be previewed instead of fully displayed."""
        large_text = "x" * 13000
        with (
            patch(
                "judge.web.services.wrong_artifacts",
                return_value={"input": large_text, "expected": "ok", "actual": large_text},
            ),
            patch("judge.web.services.wrong_diff_text", return_value=large_text),
        ):
            client = TestClient(create_app())
            response = client.get("/api/runs/run-1/wrong/001")

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["truncation"]["input"]["truncated"])
        self.assertTrue(data["truncation"]["actual"]["truncated"])
        self.assertTrue(data["truncation"]["diff"]["truncated"])
        self.assertFalse(data["truncation"]["expected"]["truncated"])
        self.assertIn("truncated after", data["input"])
        self.assertLess(len(data["input"]), len(large_text))

    def test_run_uploaded_python_submission_streams_progress(self) -> None:
        """Uploaded source runs should emit progress events and a final result."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
                "ALJ_PYTHON": sys.executable,
            }
            source = (ROOT / "tests" / "fixtures" / "accepted.py").read_bytes()
            with patch.dict(os.environ, env, clear=True):
                client = TestClient(create_app())
                response = client.post(
                    "/api/run/stream",
                    data={
                        "problem_id": "06",
                        "profile": "sample",
                        "source_mode": "upload",
                    },
                    files={"file": ("main.py", source, "text/x-python")},
                )
                self.assertEqual(response.status_code, 200, response.text)
                events = sse_events(response.text)
                self.assertTrue(any(event == "log" for event, _ in events))
                self.assertTrue(
                    any("Compiling cases.yml" in data.get("message", "") for _, data in events)
                )
                result_events = [data for event, data in events if event == "result"]
                self.assertEqual(result_events[-1]["status"], "accepted")
                self.assertEqual(result_events[-1]["profile"], "hidden")

    def test_run_pasted_python_submission_streams_progress(self) -> None:
        """Pasted source runs should use the same streaming path as uploads."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
                "ALJ_PYTHON": sys.executable,
            }
            source = (ROOT / "tests" / "fixtures" / "accepted.py").read_text(encoding="utf-8")
            with patch.dict(os.environ, env, clear=True):
                client = TestClient(create_app())
                response = client.post(
                    "/api/run/stream",
                    data={
                        "problem_id": "06",
                        "profile": "sample",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": source,
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                result_events = [
                    data for event, data in sse_events(response.text) if event == "result"
                ]
                self.assertEqual(result_events[-1]["status"], "accepted")
                self.assertEqual(result_events[-1]["profile"], "hidden")

    def test_sample_cases_endpoint_returns_visible_io(self) -> None:
        """The web API should expose sample inputs and expected outputs."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
                "ALJ_PYTHON": sys.executable,
            }
            with patch.dict(os.environ, env, clear=True):
                client = TestClient(create_app())
                response = client.get("/api/problems/06/samples")

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["profile"], "sample")
        self.assertFalse(result["cached"])
        self.assertIn("etag", result)
        self.assertIn("etag", response.headers)
        self.assertGreater(result["caseCount"], 0)
        self.assertIn("input", result["cases"][0])
        self.assertIn("expected", result["cases"][0])

    def test_sample_cases_endpoint_reuses_cached_data(self) -> None:
        """Sample loading should generate once and use the manifest cache afterward."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
                "ALJ_PYTHON": sys.executable,
            }
            with patch.dict(os.environ, env, clear=True):
                client = TestClient(create_app())
                first = client.get("/api/problems/06/samples")
                self.assertEqual(first.status_code, 200, first.text)
                self.assertFalse(first.json()["cached"])
                with patch(
                    "judge.web.services.generate",
                    side_effect=AssertionError("sample cache was bypassed"),
                ):
                    second = client.get("/api/problems/06/samples")
                    not_modified = client.get(
                        "/api/problems/06/samples",
                        headers={"If-None-Match": first.headers["etag"]},
                    )

        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(second.json()["cached"])
        self.assertEqual(second.json()["cases"][0]["input"], first.json()["cases"][0]["input"])
        self.assertEqual(not_modified.status_code, 304)
        self.assertEqual(not_modified.text, "")

    def test_debug_config_is_opt_in(self) -> None:
        """Debug UI should only be enabled when the web debug flag is set."""
        with patch.dict(os.environ, {"ALJ_WEB_DEBUG": "1"}, clear=False):
            client = TestClient(create_app())
            response = client.get("/api/status")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["config"]["webDebug"])

    def test_generate_streams_progress(self) -> None:
        """Generate should emit progress events and a final result."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
                "ALJ_PYTHON": sys.executable,
            }
            with patch.dict(os.environ, env, clear=True):
                client = TestClient(create_app())
                response = client.post(
                    "/api/generate/stream",
                    json={
                        "problem_id": "06",
                        "profile": "sample",
                        "force": True,
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                events = sse_events(response.text)
                self.assertTrue(any(event == "log" for event, _ in events))
                self.assertTrue(
                    any("Compiling cases.yml" in data.get("message", "") for _, data in events)
                )
                result_events = [data for event, data in events if event == "result"]
                self.assertGreater(result_events[-1]["caseCount"], 0)

    def test_cases_compile_endpoint(self) -> None:
        """The web API should expose structured cases.yml compile results."""
        client = TestClient(create_app())

        response = client.post(
            "/api/cases/compile",
            json={"problem_id": "06", "profile": "sample"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue(result["valid"])
        self.assertEqual(result["profiles"][0]["name"], "sample")
        self.assertGreater(result["profiles"][0]["caseCount"], 0)

    def test_cases_compile_endpoint_returns_invalid_diagnostics(self) -> None:
        """Invalid compile results should stay structured at the web boundary."""
        with patch("judge.web.services.compile_problem_cases_result") as compile_cases:
            compile_cases.return_value = {
                "valid": False,
                "path": "/tmp/cases.yml",
                "profiles": [],
                "diagnostics": [
                    {
                        "severity": "error",
                        "path": "problems/06/generator/cases.yml",
                        "line": 14,
                        "profile": "hidden",
                        "location": "cases[0].matrix",
                        "message": "matrix must be a mapping, got null",
                        "hint": "`vars`, `where`, and `item` must be indented under `matrix:`.",
                    }
                ],
            }
            client = TestClient(create_app())

            response = client.post(
                "/api/cases/compile",
                json={"problem_id": "06", "profile": "hidden"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertFalse(result["valid"])
        self.assertEqual(result["diagnostics"][0]["location"], "cases[0].matrix")

    def test_generate_stream_returns_error_when_cases_compile_fails(self) -> None:
        """Generate stream should surface cases.yml compile errors as SSE errors."""
        with patch(
            "judge.web.services.generate",
            side_effect=JudgeError("cases.yml compile failed"),
        ):
            client = TestClient(create_app())

            response = client.post(
                "/api/generate/stream",
                json={"problem_id": "06", "profile": "hidden", "force": True},
            )

        self.assertEqual(response.status_code, 200, response.text)
        events = sse_events(response.text)
        error_events = [data for event, data in events if event == "error"]
        result_events = [data for event, data in events if event == "result"]
        self.assertIn("cases.yml compile failed", error_events[-1]["message"])
        self.assertFalse(result_events)

    def test_run_stream_returns_error_when_cases_compile_fails(self) -> None:
        """Run stream should surface cases.yml compile errors as SSE errors."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "judge.web.services.run_submission",
                    side_effect=JudgeError("cases.yml compile failed"),
                ),
            ):
                client = TestClient(create_app())
                source = (ROOT / "tests" / "fixtures" / "accepted.py").read_bytes()

                response = client.post(
                    "/api/run/stream",
                    data={
                        "problem_id": "06",
                        "profile": "hidden",
                        "source_mode": "upload",
                    },
                    files={"file": ("main.py", source, "text/x-python")},
                )

        self.assertEqual(response.status_code, 200, response.text)
        events = sse_events(response.text)
        error_events = [data for event, data in events if event == "error"]
        result_events = [data for event, data in events if event == "result"]
        self.assertIn("cases.yml compile failed", error_events[-1]["message"])
        self.assertFalse(result_events)

    def test_cache_clear_all_deletes_cache_root(self) -> None:
        """Cache clear all from the web API should delete the configured cache root."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            cache = Path(tmp) / "cache"
            target = cache / "runs" / "run-1" / "result.json"
            target.parent.mkdir(parents=True)
            target.write_text("{}", encoding="utf-8")
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(cache),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with patch.dict(os.environ, env, clear=True):
                client = TestClient(create_app())
                response = client.post(
                    "/api/cache/clear",
                    json={"all_entries": True, "dry_run": False},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertFalse(cache.exists())

    def test_upload_pack_endpoint_persists_file_before_install(self) -> None:
        """Pack uploads should be saved before the installer is called."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with patch.dict(os.environ, env, clear=True):
                with patch("judge.web.services.install_problem_pack") as install:
                    install.return_value = {"installedPath": "/tmp/basic", "label": "basic"}
                    client = TestClient(create_app())
                    response = client.post(
                        "/api/packs/upload",
                        files={"file": ("basic.aljpack", b"pack-bytes", "application/gzip")},
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    uploaded_path = Path(install.call_args.args[0])
                    self.assertTrue(uploaded_path.exists())
                    self.assertEqual(uploaded_path.read_bytes(), b"pack-bytes")

    def test_download_pack_endpoint_uses_requested_repository(self) -> None:
        """Official downloads should pass repository and asset choices to the service."""
        with patch("judge.web.services.download_official_problem_pack") as download:
            download.return_value = {
                "installedPath": "/tmp/basic",
                "label": "basic",
                "repository": "tony9402/algorithm-modules",
                "assetName": "basic-1-macos-arm64.aljpack",
            }
            client = TestClient(create_app())
            response = client.post(
                "/api/packs/download",
                json={
                    "repository": "tony9402/algorithm-modules",
                    "asset_name": "basic-1-macos-arm64.aljpack",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            download.assert_called_once_with(
                "tony9402/algorithm-modules",
                "basic-1-macos-arm64.aljpack",
            )


if __name__ == "__main__":
    unittest.main()
