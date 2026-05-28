from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from judge.core.errors import JudgeError
from judge.web import services
from judge.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_INNER_HTML_SAFE_MARKERS = (
    "escapeHtml(",
    "app.escapeHtml(",
    "renderDiffArtifact(",
    "highlightCode(",
    "renderSolutionCasesBody(",
)


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


def find_statement_end(source: str, start: int) -> int:
    quote: str | None = None
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
            continue
        if char == ";":
            return index + 1
    return len(source)


def iter_inner_html_assignments(source: str) -> list[tuple[int, str]]:
    assignments = []
    cursor = 0
    marker = ".innerHTML"
    while True:
        index = source.find(marker, cursor)
        if index < 0:
            return assignments
        equals = source.find("=", index + len(marker))
        if equals < 0:
            cursor = index + len(marker)
            continue
        between = source[index + len(marker) : equals].strip()
        if between:
            cursor = index + len(marker)
            continue
        if equals + 1 < len(source) and source[equals + 1] == "=":
            cursor = equals + 1
            continue
        start = source.rfind("\n", 0, index) + 1
        end = find_statement_end(source, equals + 1)
        line = source.count("\n", 0, index) + 1
        assignments.append((line, source[start:end].strip()))
        cursor = end


def is_static_inner_html_assignment(statement: str) -> bool:
    rhs = statement.split("=", 1)[1].strip().removesuffix(";").strip()
    if rhs in {'""', "''", "``"}:
        return True
    if rhs.startswith(('"', "'")) and rhs.endswith(rhs[0]):
        return True
    return rhs.startswith("`") and rhs.endswith("`") and "${" not in rhs


class WebUiTest(unittest.TestCase):
    """Smoke tests for the local FastAPI web UI."""

    def test_project_frontend_inner_html_assignments_are_sanitized(self) -> None:
        """Dynamic innerHTML rendering should escape user/API-controlled values."""
        unsafe = []
        roots = [
            ROOT / "judge" / "web" / "static" / "app",
            ROOT / "problem_studio" / "web" / "static" / "app",
        ]
        for root in roots:
            for path in sorted(root.rglob("*.js")):
                source = path.read_text(encoding="utf-8")
                for line, statement in iter_inner_html_assignments(source):
                    if is_static_inner_html_assignment(statement):
                        continue
                    if any(marker in statement for marker in FRONTEND_INNER_HTML_SAFE_MARKERS):
                        continue
                    unsafe.append(f"{path.relative_to(ROOT)}:{line}: {statement}")

        self.assertEqual([], unsafe)

    def test_static_assets_reject_path_traversal(self) -> None:
        """Nested static asset serving should stay inside the static root."""
        client = TestClient(create_app())

        response = client.get("/static/%2E%2E/pyproject.toml")

        self.assertEqual(response.status_code, 404)

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
                self.assertIn("신뢰한 repository 또는 .aljpack만 설치하세요", page.text)
                self.assertIn("source archive로 fallback", page.text)
                self.assertIn("Cache 정리", page.text)
                self.assertIn("Samples", page.text)
                self.assertIn("themeToggleButton", page.text)
                self.assertIn("sourceLineNumbers", page.text)
                self.assertIn("sourceHighlight", page.text)
                self.assertIn("editor-toolbar", page.text)
                self.assertIn("sourceHistoryList", page.text)
                self.assertIn("sourceReadiness", page.text)
                self.assertIn("Run Tests", page.text)
                self.assertIn("jobsButton", page.text)
                self.assertIn("jobsPanel", page.text)
                self.assertIn("runProfileSelect", page.text)
                self.assertIn("toastHost", page.text)
                self.assertIn("generationProgress", page.text)
                self.assertNotIn("Refresh</button>", page.text)
                self.assertIn("/static/app.js?v=", page.text)
                app_js = client.get("/static/app.js")
                self.assertEqual(app_js.status_code, 200)
                self.assertEqual(app_js.headers.get("cache-control"), "no-store")
                self.assertIn('import "./app/state.js";', app_js.text)
                module_names = [
                    "state",
                    "dom",
                    "api",
                    "theme",
                    "editor",
                    "editor-highlight",
                    "source-readiness",
                    "editor-mode",
                    "status",
                    "status-ui",
                    "status-progress",
                    "status-debug",
                    "samples",
                    "problems",
                    "packs",
                    "cache",
                    "sources",
                    "cases",
                    "stream",
                    "jobs",
                    "generation",
                    "run",
                    "modal",
                    "refresh",
                    "events",
                ]
                module_texts = [app_js.text]
                for module_name in module_names:
                    module_response = client.get(f"/static/app/{module_name}.js")
                    self.assertEqual(module_response.status_code, 200)
                    self.assertEqual(module_response.headers.get("cache-control"), "no-store")
                    module_texts.append(module_response.text)
                script_text = "\n".join(module_texts)
                self.assertIn("function bindEvents", script_text)
                self.assertIn("function updateEditorLineNumbers", script_text)
                self.assertIn("function highlightCode", script_text)
                self.assertIn("function renderSourceHistory", script_text)
                self.assertIn("Installed source fallback", script_text)
                self.assertIn("function restoreRunResult", script_text)
                self.assertIn("function bindJobs", script_text)
                self.assertIn("/api/sources", script_text)
                self.assertIn("/api/jobs", script_text)
                self.assertIn("cancelBlockedReason", script_text)
                self.assertIn("/api/config", script_text)
                self.assertNotIn("profileSelect", script_text)
                stylesheet = client.get("/static/styles.css")
                self.assertEqual(stylesheet.status_code, 200)
                self.assertEqual(stylesheet.headers.get("cache-control"), "no-store")
                self.assertIn('@import url("./styles/base.css', stylesheet.text)
                style_names = [
                    "base",
                    "layout",
                    "forms",
                    "editor",
                    "source-history",
                    "results",
                    "jobs",
                    "badges",
                    "output",
                    "samples",
                    "status-grid",
                    "progress",
                    "artifacts",
                    "modals",
                    "responsive",
                ]
                style_texts = [stylesheet.text]
                for style_name in style_names:
                    style_response = client.get(f"/static/styles/{style_name}.css")
                    self.assertEqual(style_response.status_code, 200)
                    self.assertEqual(style_response.headers.get("cache-control"), "no-store")
                    style_texts.append(style_response.text)
                stylesheet_text = "\n".join(style_texts)
                self.assertIn(".source-history", stylesheet_text)
                self.assertIn(".code-editor", stylesheet_text)
                self.assertIn(".job-cancel-reason", stylesheet_text)
                self.assertIn(".modal", stylesheet_text)
                self.assertIn("@media (max-width: 900px)", stylesheet_text)
                status = client.get("/api/status")
                self.assertEqual(status.status_code, 200)
                data = status.json()
                self.assertIn("problems", data)
                self.assertIn("cache", data)
                self.assertIn("sources", data["cache"])
                self.assertEqual(data["config"]["sampleProfile"], "sample")
                self.assertEqual(data["config"]["judgeProfile"], "full")
                self.assertFalse(data["config"]["webDebug"])
                config = client.get("/api/config")
                self.assertEqual(config.status_code, 200)
                self.assertEqual(config.json()["judgeProfile"], "full")

    def test_problem_folder_update_allows_source_and_blocks_pack_problem(self) -> None:
        """Problem folders should be editable for source problems, not installed packs."""
        with tempfile.TemporaryDirectory(prefix="alj-web-folder-test-") as tmp:
            tmp_path = Path(tmp)
            project = tmp_path / "project"
            project.mkdir()
            source_problem = (
                tmp_path / "data" / "problem-sources" / "owner" / "repo" / "problems" / "alpha"
            )
            pack_problem = tmp_path / "data" / "problem-packs" / "basic" / "problems" / "beta"
            source_problem.mkdir(parents=True)
            pack_problem.mkdir(parents=True)
            (source_problem / "problem.json").write_text(
                '{"problemId":"alpha","title":"Alpha","folder":"Math"}',
                encoding="utf-8",
            )
            (pack_problem / "problem.json").write_text(
                '{"problemId":"beta","title":"Beta","folder":"Pack"}',
                encoding="utf-8",
            )
            env = {
                **os.environ,
                "ALJ_PROJECT_ROOT": str(project),
                "ALJ_DATA_HOME": str(tmp_path / "data"),
                "ALJ_CACHE_HOME": str(tmp_path / "cache"),
            }
            with patch.dict(os.environ, env, clear=True):
                client = TestClient(create_app())
                problems = client.get("/api/problems")
                self.assertEqual(problems.status_code, 200, problems.text)
                by_id = {problem["problemId"]: problem for problem in problems.json()}
                self.assertTrue(by_id["alpha"]["folderEditable"])
                self.assertFalse(by_id["beta"]["folderEditable"])

                moved = client.patch("/api/problems/alpha/folder", json={"folder": "Graph"})
                self.assertEqual(moved.status_code, 200, moved.text)
                self.assertEqual(moved.json()["folder"], "Graph")
                self.assertIn(
                    '"folder": "Graph"',
                    (source_problem / "problem.json").read_text(encoding="utf-8"),
                )

                blocked = client.patch("/api/problems/beta/folder", json={"folder": "Graph"})
                self.assertEqual(blocked.status_code, 403, blocked.text)
                self.assertIn(".aljpack", blocked.json()["detail"])

    def test_judge_jobs_api_lists_and_cancels_queued_job(self) -> None:
        """The generic Judge jobs API should expose queued jobs and cancel them."""
        client = TestClient(create_app())
        client.app.state.jobs.max_running_jobs = 1
        started = threading.Event()
        release = threading.Event()

        def blocking_operation() -> dict:
            started.set()
            release.wait(timeout=2)
            return {"ok": True}

        client.app.state.jobs.start(
            kind="blocker",
            title="blocker",
            problem_id="06",
            operation=blocking_operation,
        )
        self.assertTrue(started.wait(timeout=1))
        queued = client.post(
            "/api/cases/jobs",
            json={"problem_id": "06", "profile": "sample"},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        queued_job = queued.json()
        self.assertEqual(queued_job["status"], "queued")

        listed = client.get("/api/jobs")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertTrue(any(job["jobId"] == queued_job["jobId"] for job in listed.json()["jobs"]))

        active_dismiss = client.delete(f"/api/jobs/{queued_job['jobId']}")
        self.assertEqual(active_dismiss.status_code, 409, active_dismiss.text)

        cancelled = client.post(f"/api/jobs/{queued_job['jobId']}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        dismissed = client.delete(f"/api/jobs/{queued_job['jobId']}")
        self.assertEqual(dismissed.status_code, 200, dismissed.text)
        release.set()

    def test_pack_install_job_exposes_blocked_cancel_reason(self) -> None:
        """Pack installation jobs should show why cancellation is unavailable."""
        client = TestClient(create_app())
        started = threading.Event()
        release = threading.Event()

        def slow_download(*_args, **_kwargs) -> dict:
            started.set()
            release.wait(timeout=2)
            return {"installType": "pack", "assetName": "basic.aljpack"}

        with patch("judge.web.services.download_official_problem_pack", side_effect=slow_download):
            queued = client.post(
                "/api/packs/download/jobs",
                json={"repository": "tony9402/algorithm-package"},
            )
            self.assertEqual(queued.status_code, 200, queued.text)
            data = queued.json()
            self.assertFalse(data["cancelSupported"])
            self.assertEqual(data["cancelMode"], "blocked")
            self.assertIn("취소", data["cancelBlockedReason"])
            self.assertTrue(started.wait(timeout=1))

            cancel = client.post(f"/api/jobs/{data['jobId']}/cancel")
            self.assertEqual(cancel.status_code, 409, cancel.text)
            release.set()

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
                self.assertEqual(result["profile"], "sample")
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

    def test_run_defaults_to_full_profile_when_profile_is_omitted(self) -> None:
        """Web run should default to the full profile instead of hidden."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            cache = Path(tmp) / "cache"

            def fake_run_submission(source, problem_id, profile, **_kwargs):
                self.assertEqual(profile, "full")
                run_dir = cache / "runs" / "run-full"
                run_dir.mkdir(parents=True)
                (run_dir / "result.json").write_text(
                    json.dumps(
                        {
                            "runId": "run-full",
                            "problemId": problem_id,
                            "profile": profile,
                            "language": "python",
                            "status": "accepted",
                            "cases": [{"case": "001", "status": "ok"}],
                            "metrics": {"maxTimeMs": 1, "maxMemoryBytes": None},
                        }
                    ),
                    encoding="utf-8",
                )
                return run_dir

            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(cache),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch("judge.web.service_runs.run_submission", side_effect=fake_run_submission),
            ):
                client = TestClient(create_app())
                response = client.post(
                    "/api/run",
                    json={
                        "problem_id": "06",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": "print(1)\n",
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["profile"], "full")

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
                "judge.web.service_runs.wrong_artifacts",
                return_value={"input": large_text, "expected": "ok", "actual": large_text},
            ),
            patch("judge.web.service_runs.wrong_diff_text", return_value=large_text),
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
                self.assertEqual(result_events[-1]["profile"], "sample")

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
                self.assertEqual(result_events[-1]["profile"], "sample")

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
                    "judge.web.service_samples.generate",
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

    def test_non_local_binding_blocks_run_apis_without_explicit_opt_in(self) -> None:
        """Remote bindings should not expose run APIs by default."""
        client = TestClient(create_app(local_binding=False, remote_warning=True))

        run = client.post(
            "/api/run",
            json={
                "problem_id": "06",
                "profile": "sample",
                "source_mode": "text",
                "filename": "main.py",
                "source_text": "print(1)",
            },
        )
        upload = client.post(
            "/api/run/upload",
            data={"problem_id": "06", "profile": "sample"},
            files={"file": ("main.py", b"print(1)", "text/x-python")},
        )
        stream = client.post(
            "/api/run/stream",
            data={
                "problem_id": "06",
                "profile": "sample",
                "source_mode": "text",
                "filename": "main.py",
                "source_text": "print(1)",
            },
        )
        run_job = client.post(
            "/api/run/jobs",
            data={
                "problem_id": "06",
                "profile": "sample",
                "source_mode": "text",
                "filename": "main.py",
                "source_text": "print(1)",
            },
        )
        generate_job = client.post(
            "/api/generate/jobs",
            json={"problem_id": "06", "profile": "sample", "force": True},
        )
        cases_job = client.post(
            "/api/cases/jobs",
            json={"problem_id": "06", "profile": "sample"},
        )
        generic_cancel = client.post("/api/jobs/missing/cancel")
        config = client.get("/api/config")

        self.assertEqual(run.status_code, 403, run.text)
        self.assertEqual(upload.status_code, 403, upload.text)
        self.assertEqual(stream.status_code, 403, stream.text)
        self.assertEqual(run_job.status_code, 403, run_job.text)
        self.assertEqual(generate_job.status_code, 403, generate_job.text)
        self.assertEqual(cases_job.status_code, 403, cases_job.text)
        self.assertEqual(generic_cancel.status_code, 403, generic_cancel.text)
        self.assertFalse(config.json()["security"]["remoteRunAllowed"])

    def test_non_local_binding_blocks_execution_and_write_entrypoints(self) -> None:
        """Remote bindings should block generation, pack writes, cache writes, and deletes."""
        with tempfile.TemporaryDirectory(prefix="alj-web-remote-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with patch.dict(os.environ, env, clear=True):
                source_path = services.save_text_source("print(1)\n", "main.py", "06")
                source_id = source_path.parent.name
                client = TestClient(create_app(local_binding=False, remote_warning=True))

                generate = client.post(
                    "/api/generate/stream",
                    json={"problem_id": "06", "profile": "sample", "force": True},
                )
                samples = client.get("/api/problems/06/samples")
                cases_compile = client.post(
                    "/api/cases/compile",
                    json={"problem_id": "06", "profile": "sample"},
                )
                source_detail = client.get(f"/api/sources/{source_id}")
                pack_upload = client.post(
                    "/api/packs/upload",
                    files={"file": ("basic.aljpack", b"pack", "application/gzip")},
                )
                pack_upload_job = client.post(
                    "/api/packs/upload/jobs",
                    files={"file": ("basic.aljpack", b"pack", "application/gzip")},
                )
                pack_download = client.post(
                    "/api/packs/download",
                    json={"repository": "tony9402/algorithm-package"},
                )
                pack_download_job = client.post(
                    "/api/packs/download/jobs",
                    json={"repository": "tony9402/algorithm-package"},
                )
                pack_install_job = client.post(
                    "/api/packs/install/jobs",
                    json={"archive_path": str(Path(tmp) / "basic.aljpack")},
                )
                generic_dismiss = client.delete("/api/jobs/missing")
                generic_clear = client.delete("/api/jobs/completed")
                cache_clear = client.post(
                    "/api/cache/clear",
                    json={"all_entries": True, "dry_run": False},
                )
                source_delete = client.delete(f"/api/sources/{source_id}")

        self.assertEqual(generate.status_code, 403, generate.text)
        self.assertEqual(samples.status_code, 403, samples.text)
        self.assertEqual(cases_compile.status_code, 200, cases_compile.text)
        self.assertEqual(source_detail.status_code, 403, source_detail.text)
        self.assertEqual(pack_upload.status_code, 403, pack_upload.text)
        self.assertEqual(pack_upload_job.status_code, 403, pack_upload_job.text)
        self.assertEqual(pack_download.status_code, 403, pack_download.text)
        self.assertEqual(pack_download_job.status_code, 403, pack_download_job.text)
        self.assertEqual(pack_install_job.status_code, 403, pack_install_job.text)
        self.assertEqual(generic_dismiss.status_code, 403, generic_dismiss.text)
        self.assertEqual(generic_clear.status_code, 403, generic_clear.text)
        self.assertEqual(cache_clear.status_code, 403, cache_clear.text)
        self.assertEqual(source_delete.status_code, 403, source_delete.text)

    def test_non_local_binding_can_opt_in_to_run_api(self) -> None:
        """The explicit unsafe opt-in should allow non-local run APIs."""
        client = TestClient(
            create_app(
                local_binding=False,
                remote_warning=True,
                allow_remote_run=True,
            )
        )
        with patch("judge.web.services.run_problem", return_value={"status": "accepted"}):
            response = client.post(
                "/api/run",
                json={
                    "problem_id": "06",
                    "profile": "sample",
                    "source_mode": "text",
                    "filename": "main.py",
                    "source_text": "print(1)",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(client.get("/api/config").json()["security"]["remoteRunAllowed"])

    def test_source_text_and_upload_size_limits_return_413(self) -> None:
        """Oversized source text and uploads should be rejected before judging."""
        with tempfile.TemporaryDirectory(prefix="alj-web-limit-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch("judge.core.security_limits.MAX_SOURCE_TEXT_BYTES", 3),
                patch("judge.core.security_limits.MAX_SOURCE_UPLOAD_BYTES", 3),
            ):
                client = TestClient(create_app())
                local_source = Path(tmp) / "local.py"
                local_source.write_text("print(1)", encoding="utf-8")
                text_response = client.post(
                    "/api/run/stream",
                    data={
                        "problem_id": "06",
                        "profile": "sample",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": "print(1)",
                    },
                )
                upload_response = client.post(
                    "/api/run/stream",
                    data={
                        "problem_id": "06",
                        "profile": "sample",
                        "source_mode": "upload",
                    },
                    files={"file": ("main.py", b"print(1)", "text/x-python")},
                )
                path_response = client.post(
                    "/api/run",
                    json={
                        "problem_id": "06",
                        "profile": "sample",
                        "source_mode": "path",
                        "source_path": str(local_source),
                    },
                )
                history = client.get("/api/sources")
                history_root = Path(tmp) / "cache" / "web-submissions"
                partial_entries = list(history_root.iterdir()) if history_root.exists() else []

        self.assertEqual(text_response.status_code, 413, text_response.text)
        self.assertEqual(upload_response.status_code, 413, upload_response.text)
        self.assertEqual(path_response.status_code, 413, path_response.text)
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()["sources"], [])
        self.assertEqual(partial_entries, [])

    def test_pack_upload_size_limit_returns_413_without_installing(self) -> None:
        """Oversized pack uploads should not be installed."""
        with tempfile.TemporaryDirectory(prefix="alj-web-limit-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch("judge.core.security_limits.MAX_PACK_UPLOAD_BYTES", 3),
                patch("judge.web.service_uploads.install_problem_pack") as install,
            ):
                client = TestClient(create_app())
                response = client.post(
                    "/api/packs/upload",
                    files={"file": ("basic.aljpack", b"pack-bytes", "application/gzip")},
                )

        self.assertEqual(response.status_code, 413, response.text)
        install.assert_not_called()

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
            "judge.web.service_generation.generate",
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
                    "judge.web.service_runs.run_submission",
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
                with patch("judge.web.service_uploads.install_problem_pack") as install:
                    install.return_value = {"installedPath": "/tmp/basic", "label": "basic"}
                    client = TestClient(create_app())
                    response = client.post(
                        "/api/packs/upload",
                        files={"file": ("basic.aljpack", b"pack-bytes", "application/gzip")},
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["label"], "basic")
                    uploaded_path = Path(install.call_args.args[0])
                    self.assertTrue(uploaded_path.exists())
                    self.assertEqual(uploaded_path.read_bytes(), b"pack-bytes")

    def test_download_pack_endpoint_uses_requested_repository(self) -> None:
        """Official downloads should pass repository and asset choices to the service."""
        with patch("judge.web.services.download_official_problem_pack") as download:
            download.return_value = {
                "installedPath": "/tmp/basic",
                "label": "basic",
                "installType": "pack",
                "repository": "tony9402/algorithm-package",
                "assetName": "basic-1-macos-arm64.aljpack",
                "trustWarning": (
                    "Only install problem packs from repositories or files you trust; "
                    "problem tools run locally."
                ),
            }
            client = TestClient(create_app())
            response = client.post(
                "/api/packs/download",
                json={
                    "repository": "tony9402/algorithm-package",
                    "asset_name": "basic-1-macos-arm64.aljpack",
                    "ref": "main",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["installType"], "pack")
            self.assertEqual(payload["assetName"], "basic-1-macos-arm64.aljpack")
            self.assertIn("problem tools run locally", payload["trustWarning"])
            download.assert_called_once_with(
                "tony9402/algorithm-package",
                "basic-1-macos-arm64.aljpack",
                "main",
            )


if __name__ == "__main__":
    unittest.main()
