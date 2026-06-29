"""judge 웹 API와 프런트엔드 안전성, 스트리밍, 캐시, 업로드 제한 계약을 검증하는 테스트 모듈입니다."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from judge.core.errors import JudgeError
from judge.web import services
from judge.web.app import create_app
from judge.web.service_common import language_from_filename

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_INNER_HTML_SAFE_MARKERS = (
    "escapeHtml(",
    "app.escapeHtml(",
    "renderDiffArtifact(",
    "highlightCode(",
    "renderSolutionCasesBody(",
)


def sse_events(text: str) -> list[tuple[str, dict]]:
    """서버 전송 이벤트 응답 본문을 이벤트 이름과 JSON 페이로드 목록으로 파싱합니다.

    Args:
        text (str): 파일에 기록하거나 브라우저에서 기다릴 텍스트입니다.

    Returns:
        list[tuple[str, dict]]: 이벤트 이름과 JSON 페이로드를 순서대로 담은 목록입니다.
    """
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
    """JavaScript 소스에서 대입 문장의 끝 위치를 계산해 innerHTML 안전성 검사를 정확히 자릅니다.

    Args:
        source (str): 분석하거나 실행할 소스 코드 문자열입니다.
        start (int): 문장 끝 위치를 찾기 시작할 소스 문자열 인덱스입니다.

    Returns:
        int: 대입 문장이 끝나는 소스 문자열 인덱스입니다.
    """
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
    """프런트엔드 소스에서 innerHTML 대입문을 순서대로 추출해 무해화 누락을 검사합니다.

    Args:
        source (str): 분석하거나 실행할 소스 코드 문자열입니다.

    Returns:
        list[tuple[int, str]]: innerHTML 대입 위치와 문장 문자열을 순서대로 담은 목록입니다.
    """
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
    """innerHTML 대입문이 정적 초기화로 예외 처리되어도 되는지 판정합니다.

    Args:
        statement (str): 정적 HTML 대입인지 판정할 JavaScript 문장입니다.

    Returns:
        bool: 대입문이 정적 HTML 초기화로 취급되어도 되는지 여부입니다.
    """
    rhs = statement.split("=", 1)[1].strip().removesuffix(";").strip()
    if rhs in {'""', "''", "``"}:
        return True
    if rhs.startswith(('"', "'")) and rhs.endswith(rhs[0]):
        return True
    return rhs.startswith("`") and rhs.endswith("`") and "${" not in rhs


class WebUiTest(unittest.TestCase):
    """웹 화면 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_project_frontend_inner_html_assignments_are_sanitized(self) -> None:
        """프로젝트 프런트엔드 내부 HTML 대입 무해화 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """정적 자산 거부 경로 경로 순회 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        client = TestClient(create_app())

        response = client.get("/static/%2E%2E/pyproject.toml")

        self.assertEqual(response.status_code, 404)

    def test_dashboard_status_endpoint(self) -> None:
        """대시보드 상태 엔드포인트 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
                self.assertIn("예제 채점", page.text)
                self.assertIn("전체 채점", page.text)
                self.assertIn("jobsButton", page.text)
                self.assertIn("jobsPanel", page.text)
                self.assertIn("resultModal", page.text)
                self.assertIn("resultCaseResults", page.text)
                self.assertIn("runProfileSelect", page.text)
                self.assertIn("PyPy", page.text)
                self.assertNotIn("Run Profile", page.text)
                self.assertNotIn("Language Hint", page.text)
                self.assertNotIn("View Result", page.text)
                self.assertNotIn("Dismiss", page.text)
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
                self.assertIn("pypy", script_text)
                self.assertIn("PyPy", script_text)
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
                self.assertIn(".case-result-row", stylesheet_text)
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

    def test_problem_folder_update_requires_created_folder(self) -> None:
        """문제 폴더 갱신은 미리 생성한 폴더로만 허용되는지 검증합니다."""
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
                self.assertTrue(by_id["beta"]["folderEditable"])

                missing = client.patch("/api/problems/alpha/folder", json={"folder": "Graph"})
                self.assertEqual(missing.status_code, 400, missing.text)
                self.assertIn("created before moving", missing.json()["detail"])

                created = client.post("/api/folders", json={"folder": "Graph"})
                self.assertEqual(created.status_code, 200, created.text)

                moved = client.patch("/api/problems/alpha/folder", json={"folder": "Graph"})
                self.assertEqual(moved.status_code, 200, moved.text)
                self.assertEqual(moved.json()["folder"], "Graph")
                self.assertIn(
                    '"folder": "Graph"',
                    (source_problem / "problem.json").read_text(encoding="utf-8"),
                )

                pack_moved = client.patch("/api/problems/beta/folder", json={"folder": "Graph"})
                self.assertEqual(pack_moved.status_code, 200, pack_moved.text)
                self.assertEqual(pack_moved.json()["folder"], "Graph")

    def test_problem_folder_create_and_delete_confirmation_policy(self) -> None:
        """폴더 생성과 삭제 확인 정책이 빈 폴더/문제 포함 폴더를 구분하는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-web-folder-delete-test-") as tmp:
            tmp_path = Path(tmp)
            project = tmp_path / "project"
            project.mkdir()
            source_problem = (
                tmp_path / "data" / "problem-sources" / "owner" / "repo" / "problems" / "alpha"
            )
            source_problem.mkdir(parents=True)
            (source_problem / "problem.json").write_text(
                '{"problemId":"alpha","title":"Alpha","folder":"Graph"}',
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
                created = client.post("/api/folders", json={"folder": "Empty"})
                self.assertEqual(created.status_code, 200, created.text)
                folders = client.get("/api/folders")
                self.assertEqual(folders.status_code, 200, folders.text)
                self.assertIn("Empty", {item["folder"] for item in folders.json()})

                deleted_empty = client.request(
                    "DELETE",
                    "/api/folders",
                    json={"folder": "Empty", "confirm_delete_problems": False},
                )
                self.assertEqual(deleted_empty.status_code, 200, deleted_empty.text)
                self.assertTrue(deleted_empty.json()["deleted"])

                needs_confirm = client.request(
                    "DELETE",
                    "/api/folders",
                    json={"folder": "Graph", "confirm_delete_problems": False},
                )
                self.assertEqual(needs_confirm.status_code, 409, needs_confirm.text)
                self.assertIn("폴더 내 문제들이 모두 삭제됩니다", needs_confirm.text)
                self.assertEqual(needs_confirm.json()["problems"][0]["problemId"], "alpha")

                confirmed = client.request(
                    "DELETE",
                    "/api/folders",
                    json={"folder": "Graph", "confirm_delete_problems": True},
                )
                self.assertEqual(confirmed.status_code, 200, confirmed.text)
                self.assertEqual(confirmed.json()["deletedProblems"], ["alpha"])
                self.assertFalse(source_problem.exists())
                self.assertEqual(client.get("/api/problems").json(), [])

    def test_submission_rate_limit_is_per_problem(self) -> None:
        """같은 문제의 제출은 5초 안에 거절되고 다른 문제는 영향을 받지 않는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-web-rate-test-") as tmp:
            cache = Path(tmp) / "cache"
            calls: list[str] = []

            def fake_run_submission(source, problem_id, profile, **kwargs):
                calls.append(problem_id)
                self.assertFalse(kwargs.get("stop_on_first_failure", True))
                run_dir = cache / "runs" / f"run-{problem_id}-{len(calls)}"
                run_dir.mkdir(parents=True)
                (run_dir / "result.json").write_text(
                    json.dumps(
                        {
                            "runId": run_dir.name,
                            "problemId": problem_id,
                            "profile": profile,
                            "language": language_from_filename(source.name).lower(),
                            "status": "accepted",
                            "cases": [{"case": "001", "status": "ok"}],
                            "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
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
                first = client.post(
                    "/api/run",
                    json={
                        "problem_id": "06",
                        "profile": "sample",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": "print(1)\n",
                    },
                )
                second = client.post(
                    "/api/run",
                    json={
                        "problem_id": "06",
                        "profile": "sample",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": "print(1)\n",
                    },
                )
                other_problem = client.post(
                    "/api/run",
                    json={
                        "problem_id": "07",
                        "profile": "sample",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": "print(1)\n",
                    },
                )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 429, second.text)
        self.assertIn("retryAfterSeconds", second.text)
        self.assertEqual(other_problem.status_code, 200, other_problem.text)
        self.assertEqual(calls, ["06", "07"])

    def test_submission_filename_and_language_are_normalized(self) -> None:
        """명시 언어가 파일명 정규화에 우선 적용되고 확장자 호환성을 검증하는지 확인합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-web-source-name-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with patch.dict(os.environ, env, clear=True):
                python_source = services.save_text_source("print(1)\n", "main", "06", "python")
                pypy_source = services.save_text_source("print(1)\n", "main.py", "06", "pypy")
                cpp_source = services.save_text_source("int main(){}\n", "solution.cpp", "06", "cpp")
                java_source = services.save_text_source("class Main {}\n", "", "06", "java")
                with self.assertRaises(JudgeError):
                    services.save_text_source("int main(){}\n", "solution.cpp", "06", "python")
                with self.assertRaises(JudgeError):
                    services.save_text_source("x", "main.rb", "06", "python")
                with self.assertRaises(JudgeError):
                    services.save_text_source("x", "main", "06", "ruby")

        self.assertEqual(python_source.name, "main.py")
        self.assertEqual(pypy_source.name, "main.py")
        self.assertEqual(cpp_source.name, "solution.cpp")
        self.assertEqual(language_from_filename(cpp_source.name), "C++")
        self.assertEqual(java_source.name, "Main.java")

    def test_judge_jobs_api_lists_and_cancels_queued_job(self) -> None:
        """채점기 작업 API 목록 조회 및 취소 대기 중 작업 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        client = TestClient(create_app())
        client.app.state.jobs.max_running_jobs = 1
        started = threading.Event()
        release = threading.Event()

        def blocking_operation() -> dict:
            """작업 큐 취소 테스트가 실행 중 상태를 관찰할 수 있도록 이벤트가 풀릴 때까지 대기합니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
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

    def test_judge_jobs_api_paginates_judge_runs_by_newest_first(self) -> None:
        """제출 결과 API가 judge-run만 최신 제출순으로 페이지네이션하는지 검증합니다."""
        client = TestClient(create_app())
        client.app.state.jobs.start(
            kind="judge-generate",
            title="generate",
            problem_id="06",
            operation=lambda: {"ok": True},
        )
        for index in range(6):
            client.app.state.jobs.start(
                kind="judge-run",
                title=f"run-{index}",
                problem_id="06",
                operation=lambda value=index: {"index": value},
            )
            time.sleep(0.002)

        first_page = client.get("/api/jobs?kind=judge-run&page=1&page_size=3&order=queued_desc")
        second_page = client.get("/api/jobs?kind=judge-run&page=2&page_size=3&order=queued_desc")

        self.assertEqual(first_page.status_code, 200, first_page.text)
        self.assertEqual(second_page.status_code, 200, second_page.text)
        first_data = first_page.json()
        second_data = second_page.json()
        self.assertEqual(first_data["total"], 6)
        self.assertEqual(first_data["totalPages"], 2)
        self.assertEqual([job["title"] for job in first_data["jobs"]], ["run-5", "run-4", "run-3"])
        self.assertEqual([job["title"] for job in second_data["jobs"]], ["run-2", "run-1", "run-0"])
        self.assertTrue(all(job["kind"] == "judge-run" for job in first_data["jobs"]))

    def test_pack_install_job_exposes_blocked_cancel_reason(self) -> None:
        """패키지 설치 작업 노출 차단 취소 사유 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        client = TestClient(create_app())
        started = threading.Event()
        release = threading.Event()

        def slow_download(*_args, **_kwargs) -> dict:
            """패키지 설치 취소 테스트가 대기 중인 다운로드 작업을 관찰할 수 있도록 지연 응답을 만듭니다.

            Args:
                _args (tuple[Any, ...]): 테스트 대역이 호출 시그니처를 맞추기 위해 받는 사용하지 않는 위치 인자입니다.
                _kwargs (dict[str, Any]): 테스트 대역이 실제 함수 시그니처와 호환되도록 받는 사용하지 않는 키워드 인자입니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
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
        """실행 붙여넣은 Python 제출 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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

    def test_run_pasted_pypy_submission_preserves_language(self) -> None:
        """PyPy로 붙여넣은 제출이 .py 확장자 추론에 덮이지 않고 실행 언어로 전달되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-web-pypy-test-") as tmp:
            cache = Path(tmp) / "cache"

            def fake_run_submission(source, problem_id, profile, **kwargs):
                self.assertEqual(kwargs.get("language"), "pypy")
                run_dir = cache / "runs" / "run-pypy"
                run_dir.mkdir(parents=True)
                (run_dir / "result.json").write_text(
                    json.dumps(
                        {
                            "runId": "run-pypy",
                            "problemId": problem_id,
                            "profile": profile,
                            "language": kwargs.get("language"),
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
                        "profile": "sample",
                        "source_mode": "text",
                        "filename": "main.py",
                        "language": "pypy",
                        "source_text": "print(1)\n",
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result["language"], "pypy")
                sources = client.get("/api/sources")
                self.assertEqual(sources.status_code, 200, sources.text)
                source_entry = sources.json()["sources"][0]
                self.assertEqual(source_entry["filename"], "main.py")
                self.assertEqual(source_entry["language"], "PyPy")
                self.assertEqual(source_entry["languageId"], "pypy")
                self.assertEqual(source_entry["lastRun"]["language"], "pypy")

    def test_run_defaults_to_full_profile_when_profile_is_omitted(self) -> None:
        """실행 기본값 전체 프로필 프로필 생략 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-web-test-") as tmp:
            cache = Path(tmp) / "cache"

            def fake_run_submission(source, problem_id, profile, **_kwargs):
                """실제 채점 실행을 대체해 웹 API와 솔루션 검증 테스트가 고정된 실행 결과를 받게 합니다.

                Args:
                    source (Any): 분석하거나 실행할 소스 코드 문자열입니다.
                    problem_id (Any): 테스트가 생성하거나 조회할 문제 식별자입니다.
                    profile (Any): 검증이나 실행에 사용할 테스트 프로필 이름입니다.
                    _kwargs (dict[str, Any]): 테스트 대역이 실제 함수 시그니처와 호환되도록 받는 사용하지 않는 키워드 인자입니다.

                Returns:
                    Any: 테스트 대상 API가 실제 실행 결과처럼 소비할 수 있는 결정적 결과 데이터입니다.
                """
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
        """캐시된 소스 가능 삭제 개별 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """오답 케이스 엔드포인트 잘라냄 큰 산출물 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """실행 업로드된 Python 제출 스트리밍 진행 상황 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """실행 붙여넣은 Python 제출 스트리밍 진행 상황 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """샘플 케이스 엔드포인트 반환 표시 입출력 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """샘플 케이스 엔드포인트 재사용 캐시된 데이터 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """디버그 설정 선택 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with patch.dict(os.environ, {"ALJ_WEB_DEBUG": "1"}, clear=False):
            client = TestClient(create_app())
            response = client.get("/api/status")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["config"]["webDebug"])

    def test_non_local_binding_blocks_run_apis_without_explicit_opt_in(self) -> None:
        """비 로컬 바인딩 차단 실행 API 없이 명시적 선택 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """비 로컬 바인딩 차단 실행 및 쓰기 진입점 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """비 로컬 바인딩 가능 선택 실행 API 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-web-remote-run-test-") as tmp:
            cache = Path(tmp) / "cache"

            def fake_run_submission(source, problem_id, profile, **_kwargs):
                run_dir = cache / "runs" / "remote-run"
                run_dir.mkdir(parents=True)
                (run_dir / "result.json").write_text(
                    json.dumps(
                        {
                            "runId": "remote-run",
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
                client = TestClient(
                    create_app(
                        local_binding=False,
                        remote_warning=True,
                        allow_remote_run=True,
                    )
                )
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
                config = client.get("/api/config")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(config.json()["security"]["remoteRunAllowed"])

    def test_source_text_and_upload_size_limits_return_413(self) -> None:
        """소스 텍스트 및 업로드 크기 제한 반환 413 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """패키지 업로드 크기 한도 반환 413 없이 설치 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """생성 스트리밍 진행 상황 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """케이스 컴파일 엔드포인트 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """케이스 컴파일 엔드포인트 반환 잘못된 진단 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """생성 스트림 반환 오류 케이스 컴파일 실패 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """실행 스트림 반환 오류 케이스 컴파일 실패 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """캐시 삭제 전체 삭제 캐시 루트 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """업로드 패키지 엔드포인트 저장 파일 전에 설치 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """다운로드 패키지 엔드포인트 사용 요청된 저장소 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
