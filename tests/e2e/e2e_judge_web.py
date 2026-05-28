from __future__ import annotations

from judge.web.app import create_app
from tests.e2e.helpers import (
    ROOT,
    BrowserE2ETestCase,
    assert_no_overlap,
    assert_visible_in_viewport,
    create_minimal_pack,
    isolated_runtime,
    judge_env,
    run_app,
    temporary_env,
    wait_for_text,
)

VALID_CASES_COMPILE = {
    "valid": True,
    "path": "/tmp/cases.yml",
    "profiles": [{"name": "full", "caseCount": 1, "cases": []}],
    "diagnostics": [],
}


def stub_samples(page) -> None:
    page.route(
        "**/api/problems/06/samples**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=(
                '{"profile":"sample","caseCount":1,"label":"e2e",'
                '"cases":[{"case":"001","name":"stub","input":"1 1\\n",'
                '"expected":"1\\n"}]}'
            ),
        ),
    )


def route_jobs_list(page, jobs: dict[str, dict]) -> None:
    page.route("**/api/jobs", lambda route: route.fulfill(json={"jobs": list(jobs.values())}))


def completed_job(
    job_id: str,
    kind: str,
    title: str,
    result: dict,
    *,
    problem_id: str = "06",
    target: dict | None = None,
) -> dict:
    return {
        "jobId": job_id,
        "kind": kind,
        "title": title,
        "problemId": problem_id,
        "status": "succeeded",
        "cancelSupported": True,
        "target": target or {"problemId": problem_id},
        "progress": {"message": "job finished"},
        "lastLog": "job finished",
        "logs": [{"message": "job finished"}],
        "result": result,
    }


class JudgeWebE2ETest(BrowserE2ETestCase):
    def test_selected_problem_is_restored_after_reload_in_browser(self) -> None:
        sample_payload = (
            '{"profile":"sample","caseCount":1,"label":"persist",'
            '"cases":[{"case":"001","name":"persist","input":"1\\n","expected":"1\\n"}]}'
        )
        with isolated_runtime("alj-judge-web-selection-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                page.route(
                    "**/api/problems",
                    lambda route: route.fulfill(
                        json=[
                            {
                                "problemId": "06",
                                "title": "Default",
                                "version": 1,
                                "defaultProfile": "full",
                                "profiles": ["sample", "hidden"],
                            },
                            {
                                "problemId": "persist",
                                "title": "Persisted",
                                "version": 1,
                                "defaultProfile": "full",
                                "profiles": ["sample", "hidden"],
                            },
                        ]
                    ),
                )
                page.route(
                    "**/api/problems/*/samples**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=sample_payload,
                    ),
                )
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("persist")
                wait_for_text(page, "#problemList", "Persisted")
                page.wait_for_function(
                    "() => localStorage.getItem('alj:selected-problem:v1') === 'persist'"
                )
                page.wait_for_function(
                    "() => new URL(window.location.href).searchParams.get('problem') === 'persist'"
                )

                page.reload()
                page.locator("#runButton").wait_for(state="visible")
                page.wait_for_function(
                    "() => document.querySelector('#problemSelect')?.value === 'persist'"
                )
                self.assertTrue(
                    page.locator('[data-problem-id="persist"]').evaluate(
                        "node => node.classList.contains('active')"
                    )
                )
                wait_for_text(page, "#sampleMeta", "persist")
                self.assert_no_browser_errors()

    def test_problem_folder_drag_drop_updates_problem_metadata_in_browser(self) -> None:
        problems = [
            {
                "problemId": "alpha",
                "title": "Alpha",
                "version": 1,
                "defaultProfile": "full",
                "profiles": ["sample"],
                "folder": "Math",
                "folderEditable": True,
            },
            {
                "problemId": "beta",
                "title": "Beta",
                "version": 1,
                "defaultProfile": "full",
                "profiles": ["sample"],
                "folder": "Graph",
                "folderEditable": True,
            },
        ]
        captured: dict[str, object] = {}

        def update_folder(route):
            body = route.request.post_data_json
            problem_id = route.request.url.split("/api/problems/", 1)[1].split("/", 1)[0]
            captured["problemId"] = problem_id
            captured["folder"] = body["folder"]
            for problem in problems:
                if problem["problemId"] == problem_id:
                    problem["folder"] = body["folder"]
                    route.fulfill(json=problem)
                    return
            route.fulfill(status=404, json={"detail": "not found"})

        with isolated_runtime("alj-judge-web-folder-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                page.route("**/api/problems", lambda route: route.fulfill(json=problems))
                page.route("**/api/problems/*/folder", update_folder)
                page.route(
                    "**/api/problems/*/samples**",
                    lambda route: route.fulfill(
                        json={
                            "profile": "sample",
                            "caseCount": 0,
                            "label": "folder",
                            "cases": [],
                        }
                    ),
                )
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                wait_for_text(page, "#problemList", "Math")
                wait_for_text(page, "#problemList", "Graph")

                page.evaluate(
                    """() => {
                        const source = document.querySelector('[data-problem-id="alpha"]');
                        const target = [...document.querySelectorAll('.problem-folder-group')]
                          .find((group) => group.dataset.folder === 'Graph');
                        const dataTransfer = new DataTransfer();
                        source.dispatchEvent(new DragEvent('dragstart', {
                          bubbles: true,
                          cancelable: true,
                          dataTransfer,
                        }));
                        target.dispatchEvent(new DragEvent('dragover', {
                          bubbles: true,
                          cancelable: true,
                          dataTransfer,
                        }));
                        target.dispatchEvent(new DragEvent('drop', {
                          bubbles: true,
                          cancelable: true,
                          dataTransfer,
                        }));
                        source.dispatchEvent(new DragEvent('dragend', {
                          bubbles: true,
                          cancelable: true,
                          dataTransfer,
                        }));
                    }"""
                )
                wait_for_text(page, "#toastHost", "alpha folder moved to Graph")
                self.assertEqual(captured, {"problemId": "alpha", "folder": "Graph"})
                self.assertEqual(
                    page.locator('.problem-folder-group[data-folder="Graph"] .list-item').count(),
                    2,
                )

                page.locator("#problemSelect").select_option("alpha")
                page.locator("#problemFolderInput").fill("Dynamic")
                page.locator("#problemFolderSaveButton").click()
                wait_for_text(page, "#toastHost", "alpha folder moved to Dynamic")
                self.assertEqual(captured, {"problemId": "alpha", "folder": "Dynamic"})
                self.assert_no_browser_errors()

    def test_pasted_source_runs_and_updates_history_in_browser(self) -> None:
        source = (ROOT / "tests" / "fixtures" / "accepted.py").read_text(encoding="utf-8")
        with isolated_runtime("alj-judge-web-e2e-") as (_directory, runtime):
            env = judge_env(runtime)
            with temporary_env(env), run_app(create_app()) as server:
                page = self.new_page(server.url)
                page.goto(server.url)

                page.locator("#runButton").wait_for(state="visible")
                page.wait_for_function(
                    """() => document.querySelector("#problemSelect")?.options.length > 0"""
                )
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                page.locator("#textModeButton").click()
                page.locator("#filenameInput").fill("main.py")
                page.locator("#sourceTextInput").fill(source)

                wait_for_text(page, "#sourceReadiness", "main.py ready")
                page.locator("#runButton").click()
                wait_for_text(page, "#statusBadge", "accepted", timeout=120_000)
                wait_for_text(page, "#resultSummary", "Accepted", timeout=120_000)
                wait_for_text(page, "#sourceHistoryList", "main.py", timeout=120_000)
                wait_for_text(page, "#sourceHistoryList", "accepted", timeout=120_000)
                wait_for_text(page, "#sampleCases", "Input")

                page.locator("#cacheManageButton").click()
                page.on("dialog", lambda dialog: dialog.accept())
                page.locator("#cacheClearAllButton").click()
                wait_for_text(page, "#cacheOutput", "Deleted", timeout=30_000)
                wait_for_text(page, "#sourceHistoryList", "No cached sources")
                page.keyboard.press("Escape")

                page.locator("#themeToggleButton").click()
                theme = page.evaluate("() => document.documentElement.dataset.theme")
                page.reload()
                page.locator("#runButton").wait_for(state="visible")
                reloaded_theme = page.evaluate("() => document.documentElement.dataset.theme")
                self.assertEqual(reloaded_theme, theme)
                self.assert_no_browser_errors()

    def test_uploaded_source_history_load_delete_and_cache_modal_in_browser(self) -> None:
        source_path = ROOT / "tests" / "fixtures" / "accepted.py"
        with isolated_runtime("alj-judge-web-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.wait_for_function(
                    """() => document.querySelector("#problemSelect")?.options.length > 0"""
                )
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                page.locator("#sourceFileInput").set_input_files(str(source_path))
                wait_for_text(page, "#sourceReadiness", "accepted.py ready")
                page.locator("#runButton").click()
                wait_for_text(page, "#statusBadge", "accepted", timeout=120_000)
                wait_for_text(page, "#sourceHistoryList", "accepted.py", timeout=120_000)

                page.reload()
                page.locator("#runButton").wait_for(state="visible")
                page.wait_for_function(
                    """() => document.querySelector("#problemSelect")?.options.length > 0"""
                )
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                wait_for_text(page, "#sourceHistoryList", "accepted.py", timeout=120_000)
                page.get_by_role("button", name="Use Code").first.click()
                wait_for_text(page, "#sourceReadiness", "accepted.py ready")
                page.wait_for_function(
                    """() => document
                        .querySelector("#sourceTextInput")
                        ?.value.includes("def main")"""
                )
                wait_for_text(page, "#sampleCases", "Input")
                self.assertIn("def main", page.locator("#sourceTextInput").input_value())
                wait_for_text(page, "#resultSummary", "Accepted")
                wait_for_text(page, "#resultMeta", "06")

                page.get_by_role("button", name="Delete").first.click()
                wait_for_text(page, "#toastHost", "Cached source deleted")
                wait_for_text(page, "#sourceHistoryList", "No cached sources")

                page.locator("#cacheManageButton").click()
                page.locator("#cachePreviewButton").click()
                wait_for_text(page, "#cacheOutput", "Will delete")
                page.on("dialog", lambda dialog: dialog.accept())
                page.locator("#cacheClearRunsButton").click()
                wait_for_text(page, "#cacheOutput", "Deleted")
                self.assert_no_browser_errors()

    def test_wrong_answer_artifacts_and_pack_install_ui_in_browser(self) -> None:
        wrong_source = "print(42)\n"
        with isolated_runtime("alj-judge-web-e2e-") as (_directory, runtime):
            pack_path = create_minimal_pack(runtime / "e2e-pack.aljpack")
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                page.locator("#textModeButton").click()
                page.locator("#filenameInput").fill("wrong.py")
                page.locator("#sourceTextInput").fill(wrong_source)
                wait_for_text(page, "#sourceReadiness", "wrong.py ready")
                page.locator("#runButton").click()
                wait_for_text(page, "#statusBadge", "wrong answer", timeout=120_000)
                wait_for_text(page, "#sourceHistoryList", "wrong.py", timeout=120_000)
                page.locator("#sourceHistoryStatusFilter").select_option("wrong_answer")
                wait_for_text(page, "#sourceHistoryList", "wrong.py")
                page.locator("#sourceHistoryFilterInput").fill("not-present")
                wait_for_text(page, "#sourceHistoryList", "No cached sources match filters")
                page.locator("#sourceHistoryFilterInput").fill("wrong")
                wait_for_text(page, "#sourceHistoryList", "wrong.py")
                wait_for_text(page, "#wrongPanel", "Wrong Case", timeout=120_000)
                page.get_by_role("button", name="Actual").click()
                wait_for_text(page, "#artifactOutput", "42", timeout=120_000)
                page.locator("#artifactCopyButton").click()
                wait_for_text(page, "#toastHost", "Copied actual artifact")
                page.locator("#artifactWrapButton").click()
                self.assertTrue(
                    page.locator("#artifactOutput").evaluate(
                        "node => node.classList.contains('wrapped')"
                    )
                )
                page.get_by_role("button", name="Diff").click()
                wait_for_text(page, "#artifactOutput", "-", timeout=120_000)
                self.assertGreater(page.locator("#artifactOutput .diff-remove").count(), 0)
                with page.expect_download() as download_info:
                    page.locator("#artifactDownloadButton").click()
                self.assertIn("diff", download_info.value.suggested_filename)

                page.locator("#addProblemButton").click()
                page.locator("#packFileInput").set_input_files(str(pack_path))
                page.locator("#uploadPackButton").click()
                wait_for_text(page, "#packStatus", "Installed pack:", timeout=30_000)
                wait_for_text(page, "#problemList", "e2e", timeout=30_000)
                self.assert_no_browser_errors()

    def test_generate_stream_success_updates_progress_in_browser(self) -> None:
        with isolated_runtime("alj-judge-web-generate-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                page.locator(".advanced-run-options > summary").click()
                page.locator("#forceGenerateInput").check()
                page.locator("#generateButton").click()
                wait_for_text(page, "#statusBadge", "Generated", timeout=120_000)
                wait_for_text(page, "#dataStatusValue", "Generated", timeout=120_000)
                wait_for_text(page, "#resultSummary", "sample test data ready", timeout=120_000)
                wait_for_text(page, "#generationProgress", "/")
                self.assert_no_browser_errors()

    def test_run_job_queue_is_visible_and_cancelable_in_browser(self) -> None:
        source = "print(1)\n"
        jobs = {}

        def listed_jobs():
            return {"jobs": list(jobs.values())}

        def create_cases_job(route):
            job = {
                "jobId": "cases-1",
                "kind": "judge-cases-compile",
                "title": "Check Cases · 06",
                "problemId": "06",
                "status": "succeeded",
                "cancelSupported": True,
                "target": {"problemId": "06", "profile": "sample"},
                "progress": {"message": "cases.yml compile finished"},
                "lastLog": "cases.yml compile finished",
                "result": VALID_CASES_COMPILE,
            }
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        def create_run_job(route):
            job = {
                "jobId": "run-1",
                "kind": "judge-run",
                "title": "Run Tests · 06",
                "problemId": "06",
                "status": "running",
                "cancelSupported": True,
                "target": {"problemId": "06", "profile": "sample", "source": "main.py"},
                "progress": {"message": "Starting judge run."},
                "lastLog": "Starting judge run.",
                "result": None,
            }
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        def cancel_job(route):
            job = jobs["run-1"]
            job["status"] = "cancelled"
            job["cancelRequested"] = True
            job["lastLog"] = "Cancel requested."
            route.fulfill(json=job)

        with isolated_runtime("alj-judge-web-job-cancel-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                page.route("**/api/cases/jobs", create_cases_job)
                page.route("**/api/run/jobs", create_run_job)
                page.route("**/api/jobs/run-1/cancel", cancel_job)
                page.route("**/api/jobs", lambda route: route.fulfill(json=listed_jobs()))
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                page.locator("#textModeButton").click()
                page.locator("#filenameInput").fill("main.py")
                page.locator("#sourceTextInput").fill(source)
                page.locator("#runButton").click()
                wait_for_text(page, "#jobsPanel", "Run Tests")
                wait_for_text(page, "#jobsPanel", "Running")
                self.assertFalse(page.locator("#sourceTextInput").is_disabled())
                page.locator('[data-job-cancel="run-1"]').click()
                page.locator('[data-job-filter="done"]').click()
                wait_for_text(page, "#jobsPanel", "Cancelled")
                self.assert_no_browser_errors()

    def test_cases_compile_failure_blocks_run_stream_in_browser(self) -> None:
        source = (ROOT / "tests" / "fixtures" / "accepted.py").read_text(encoding="utf-8")
        run_stream_called = {"value": False}
        invalid_compile = {
            "valid": False,
            "path": "/tmp/cases.yml",
            "profiles": [],
            "diagnostics": [
                {
                    "severity": "error",
                    "path": "problems/06/generator/cases.yml",
                    "line": 4,
                    "profile": "hidden",
                    "location": "cases[0].matrix",
                    "message": "forced compile failure",
                    "hint": "fix cases.yml",
                }
            ],
        }
        jobs: dict[str, dict] = {}

        with isolated_runtime("alj-judge-web-invalid-cases-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                route_jobs_list(page, jobs)

                def invalid_cases_job(route):
                    job = completed_job(
                        "cases-invalid",
                        "judge-cases-compile",
                        "Check Cases · 06",
                        invalid_compile,
                    )
                    jobs[job["jobId"]] = job
                    route.fulfill(json=job)

                page.route("**/api/cases/jobs", invalid_cases_job)

                def fail_if_run_job(route):
                    run_stream_called["value"] = True
                    route.fulfill(
                        status=500,
                        content_type="application/json",
                        body='{"detail":"run job should not be called"}',
                    )

                page.route("**/api/run/jobs", fail_if_run_job)
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                page.locator("#textModeButton").click()
                page.locator("#filenameInput").fill("main.py")
                page.locator("#sourceTextInput").fill(source)
                page.locator("#runButton").click()
                wait_for_text(page, "#statusBadge", "Cases Invalid")
                wait_for_text(page, "#resultSummary", "forced compile failure")
                self.assertFalse(run_stream_called["value"])
                self.assert_no_browser_errors()

    def test_run_stream_error_event_is_visible_in_browser(self) -> None:
        captured_run_request = {"body": ""}
        jobs: dict[str, dict] = {}

        def run_job_handler(route):
            captured_run_request["body"] = route.request.post_data or ""
            job = completed_job(
                "run-error",
                "judge-run",
                "Run Tests · 06",
                {},
                target={"problemId": "06", "profile": "sample", "source": "main.cpp"},
            )
            job["status"] = "failed"
            job["error"] = "compile failed: main.cpp"
            job["lastLog"] = "Compiling submitted source."
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        with isolated_runtime("alj-judge-web-error-event-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                route_jobs_list(page, jobs)
                page.route(
                    "**/api/cases/jobs",
                    lambda route: (
                        jobs.setdefault(
                            "cases-ok",
                            completed_job(
                                "cases-ok",
                                "judge-cases-compile",
                                "Check Cases · 06",
                                VALID_CASES_COMPILE,
                            ),
                        ),
                        route.fulfill(json=jobs["cases-ok"]),
                    ),
                )
                page.route("**/api/run/jobs", run_job_handler)
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                page.locator("#textModeButton").click()
                page.locator("#filenameInput").fill("main.cpp")
                page.locator("#sourceTextInput").fill("int main( { return 0; }\n")

                page.locator("#runButton").click()
                wait_for_text(page, "#statusBadge", "Error")
                wait_for_text(page, "#resultSummary", "compile failed: main.cpp")
                self.assertIn('name="profile"', captured_run_request["body"])
                self.assertIn("sample", captured_run_request["body"])
                self.assert_no_browser_errors()

    def test_runtime_and_time_limit_result_states_render_in_browser(self) -> None:
        scenarios = [
            ("runtime_error", "Runtime crashed"),
            ("time_limit", "Time limit exceeded"),
        ]
        for status, message in scenarios:
            with self.subTest(status=status):
                jobs: dict[str, dict] = {}

                def make_run_job_handler(status_value, message_value, job_map=jobs):
                    def fulfill_run_job(route):
                        result = {
                            "runId": f"run-{status_value}",
                            "problemId": "06",
                            "profile": "hidden",
                            "language": "Python",
                            "status": status_value,
                            "caseCount": 1,
                            "cases": [
                                {
                                    "case": "001",
                                    "status": status_value,
                                    "message": message_value,
                                    "timeMs": 1,
                                    "memoryBytes": 1024,
                                }
                            ],
                            "metrics": {
                                "maxTimeLabel": "1 ms",
                                "maxMemoryLabel": "1 KiB",
                            },
                            "message": message_value,
                            "firstFailedCase": None,
                        }
                        job = completed_job(
                            f"run-{status_value}",
                            "judge-run",
                            "Run Tests · 06",
                            result,
                        )
                        job["lastLog"] = "Running case 001 (1/1)."
                        job_map[job["jobId"]] = job
                        route.fulfill(json=job)

                    return fulfill_run_job

                with isolated_runtime(f"alj-judge-web-{status}-e2e-") as (_directory, runtime):
                    with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                        page = self.new_page(server.url)
                        stub_samples(page)
                        route_jobs_list(page, jobs)

                        def fulfill_cases_job(route, _request=None, job_map=jobs):
                            job = job_map.setdefault(
                                "cases-ok",
                                completed_job(
                                    "cases-ok",
                                    "judge-cases-compile",
                                    "Check Cases · 06",
                                    VALID_CASES_COMPILE,
                                ),
                            )
                            route.fulfill(json=job)

                        page.route("**/api/cases/jobs", fulfill_cases_job)
                        page.route(
                            "**/api/run/jobs",
                            make_run_job_handler(status, message),
                        )
                        page.goto(server.url)
                        page.locator("#runButton").wait_for(state="visible")
                        page.locator("#problemSelect").select_option("06")
                        page.locator("#textModeButton").click()
                        page.locator("#filenameInput").fill("main.py")
                        page.locator("#sourceTextInput").fill("raise SystemExit(1)\n")

                        page.locator("#runButton").click()
                        wait_for_text(page, "#statusBadge", status.replace("_", " "))
                        wait_for_text(page, "#judgeStatusValue", status.replace("_", " "))
                        wait_for_text(page, "#resultSummary", status.replace("_", " "))
                        self.assert_no_browser_errors()

    def test_official_pack_download_ui_uses_repository_asset_and_ref(self) -> None:
        captured: dict[str, object] = {}
        jobs: dict[str, dict] = {}

        def capture_download(route):
            captured["body"] = route.request.post_data_json
            job = completed_job(
                "pack-download",
                "judge-pack-download",
                "Install Official Problems",
                {
                    "assetName": "official-e2e.aljpack",
                    "label": "downloads/official-e2e.aljpack",
                    "checksumVerified": True,
                },
                problem_id="__packs__",
                target={"repository": "owner/problems", "assetName": "official-e2e.aljpack"},
            )
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        with isolated_runtime("alj-judge-web-official-pack-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                route_jobs_list(page, jobs)
                page.route("**/api/packs/download/jobs", capture_download)
                page.route(
                    "**/api/packs",
                    lambda route: route.fulfill(
                        json=[
                            {
                                "packId": "official-e2e",
                                "version": "1",
                                "supportedPlatforms": ["mock-platform"],
                                "problems": ["official-01"],
                            }
                        ]
                    ),
                )
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")

                page.locator("#addProblemButton").click()
                page.locator("#officialRepoInput").fill("owner/problems")
                page.locator("#packAssetInput").fill("official-e2e.aljpack")
                page.locator("#packRefInput").fill("v1.2.3")
                page.locator("#downloadPackButton").click()

                wait_for_text(page, "#packStatus", "official-e2e.aljpack")
                wait_for_text(page, "#packStatus", "checksum verified")
                wait_for_text(page, "#packList", "official-e2e")
                self.assertEqual(
                    captured["body"],
                    {
                        "repository": "owner/problems",
                        "asset_name": "official-e2e.aljpack",
                        "ref": "v1.2.3",
                    },
                )
                self.assert_no_browser_errors()

    def test_official_pack_download_error_guidance_in_browser(self) -> None:
        jobs: dict[str, dict] = {}

        def fail_download(route):
            job = completed_job(
                "pack-download-failed",
                "judge-pack-download",
                "Install Official Problems",
                {},
                problem_id="__packs__",
            )
            job["status"] = "failed"
            job["error"] = "release asset not found"
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        with isolated_runtime("alj-judge-web-official-pack-error-e2e-") as (
            _directory,
            runtime,
        ):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                route_jobs_list(page, jobs)
                page.route("**/api/packs/download/jobs", fail_download)
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")

                page.locator("#addProblemButton").click()
                page.locator("#officialRepoInput").fill("owner/problems")
                page.locator("#packAssetInput").fill("missing.aljpack")
                page.locator("#downloadPackButton").click()

                wait_for_text(page, "#packStatus", "repository, ref, or release asset")
                wait_for_text(page, "#packStatus", "Check the repository")
                unexpected_errors = [
                    error
                    for error in self.browser_errors
                    if "api/packs/download" not in error and "404 (Not Found)" not in error
                ]
                self.assertEqual(unexpected_errors, [])

    def test_real_compile_error_source_is_visible_in_browser(self) -> None:
        with isolated_runtime("alj-judge-web-real-compile-error-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#textModeButton").click()
                page.locator("#filenameInput").fill("main.cpp")
                page.locator("#sourceTextInput").fill("int main( { return 0; }\n")

                page.locator("#runButton").click()
                wait_for_text(page, "#statusBadge", "Error", timeout=120_000)
                wait_for_text(page, "#resultSummary", "compile failed", timeout=120_000)
                self.assert_no_browser_errors()

    def test_drag_drop_upload_and_debug_mode_render_logs(self) -> None:
        debug_env = {"ALJ_WEB_DEBUG": "1"}
        source = (ROOT / "tests" / "fixtures" / "accepted.py").read_text(encoding="utf-8")
        with isolated_runtime("alj-judge-web-debug-drop-e2e-") as (_directory, runtime):
            env = judge_env(runtime)
            env.update(debug_env)
            with temporary_env(env), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                page.locator("#debugToggle").wait_for(state="visible")
                page.locator("#debugModeInput").check()
                page.evaluate(
                    """([selector, name, content]) => {
                        const file = new File([content], name, { type: "text/x-python" });
                        const dataTransfer = new DataTransfer();
                        dataTransfer.items.add(file);
                        const event = new DragEvent("drop", {
                            bubbles: true,
                            cancelable: true,
                            dataTransfer,
                        });
                        document.querySelector(selector).dispatchEvent(event);
                    }""",
                    ["#uploadSourcePanel", "drop_accepted.py", source],
                )
                wait_for_text(page, "#sourceReadiness", "drop_accepted.py ready")

                page.locator("#runButton").click()
                wait_for_text(page, "#statusBadge", "accepted", timeout=120_000)
                wait_for_text(page, "#resultOutput", "Starting judge run.", timeout=120_000)
                self.assert_no_browser_errors()

    def test_static_modules_and_styles_load_without_browser_errors(self) -> None:
        static_urls: set[str] = set()
        with isolated_runtime("alj-judge-web-static-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                page.on(
                    "response",
                    lambda response: (
                        static_urls.add(response.url)
                        if "/static/app/" in response.url or "/static/styles/" in response.url
                        else None
                    ),
                )
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.wait_for_load_state("networkidle")
                self.assertTrue(any(url.endswith("/static/app/state.js") for url in static_urls))
                self.assertTrue(any(url.endswith("/static/app/run.js") for url in static_urls))
                for module_name in (
                    "editor-highlight",
                    "source-readiness",
                    "editor-mode",
                    "status-ui",
                    "status-progress",
                    "status-debug",
                ):
                    self.assertTrue(
                        any(url.endswith(f"/static/app/{module_name}.js") for url in static_urls)
                    )
                self.assertTrue(any("/static/styles/base.css" in url for url in static_urls))
                self.assertTrue(any("/static/styles/results.css" in url for url in static_urls))
                for style_name in (
                    "badges",
                    "output",
                    "samples",
                    "status-grid",
                    "progress",
                    "artifacts",
                ):
                    self.assertTrue(
                        any(f"/static/styles/{style_name}.css" in url for url in static_urls)
                    )
                self.assert_no_browser_errors()

    def test_problem_and_pack_metadata_escapes_html_in_browser(self) -> None:
        malicious_img = '<img src=x onerror="window.__aljXss = true">'
        cache_payload = {
            "totalSizeLabel": "0 B",
            "problems": [],
            "runs": {"count": 0, "sizeLabel": "0 B"},
            "sources": {"count": 0, "sizeLabel": "0 B"},
        }
        samples_payload = {
            "profile": "sample",
            "caseCount": 0,
            "label": "stub",
            "cases": [],
        }
        with isolated_runtime("alj-judge-web-xss-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                page.route(
                    "**/api/problems",
                    lambda route: route.fulfill(
                        json=[
                            {
                                "problemId": "xss-problem",
                                "title": malicious_img,
                                "version": malicious_img,
                                "profiles": ["sample"],
                            }
                        ],
                    ),
                )
                page.route(
                    "**/api/packs",
                    lambda route: route.fulfill(
                        json=[
                            {
                                "packId": "xss-pack",
                                "version": malicious_img,
                                "supportedPlatforms": [malicious_img],
                                "problems": [malicious_img],
                            }
                        ],
                    ),
                )
                page.route("**/api/cache", lambda route: route.fulfill(json=cache_payload))
                page.route("**/api/sources", lambda route: route.fulfill(json={"sources": []}))
                page.route(
                    "**/api/problems/xss-problem/samples**",
                    lambda route: route.fulfill(json=samples_payload),
                )

                page.goto(server.url)
                wait_for_text(page, "#problemList", "xss-problem")
                wait_for_text(page, "#packList", "xss-pack")
                page.wait_for_timeout(200)

                self.assertFalse(page.evaluate("() => Boolean(window.__aljXss)"))
                self.assertNotIn("<img", page.locator("#problemList").inner_html())
                self.assertNotIn("<img", page.locator("#packList").inner_html())
                self.assertIn("&lt;img", page.locator("#problemList").inner_html())
                self.assertIn("&lt;img", page.locator("#packList").inner_html())
                self.assert_no_browser_errors()

    def test_invalid_pack_upload_shows_modal_error_in_browser(self) -> None:
        with isolated_runtime("alj-judge-web-invalid-pack-e2e-") as (_directory, runtime):
            invalid_pack = runtime / "not-a-pack.txt"
            invalid_pack.write_text("not a pack", encoding="utf-8")
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#addProblemButton").click()
                page.locator("#packFileInput").set_input_files(str(invalid_pack))
                page.locator("#uploadPackButton").click()
                wait_for_text(page, "#packStatus", ".aljpack", timeout=30_000)
                wait_for_text(page, "#toastHost", ".aljpack", timeout=30_000)
                self.assertFalse(
                    [error for error in self.browser_errors if error.startswith("pageerror:")]
                )

    def test_truncated_wrong_artifacts_are_displayed_in_browser(self) -> None:
        source = "print(42)\n"
        valid_compile = {
            "valid": True,
            "path": "/tmp/cases.yml",
            "profiles": [{"name": "hidden", "caseCount": 1, "cases": []}],
            "diagnostics": [],
        }
        run_result = {
            "runId": "run-big",
            "problemId": "06",
            "profile": "hidden",
            "language": "python",
            "status": "wrong_answer",
            "cases": [
                {
                    "case": "001",
                    "status": "wrong_answer",
                    "message": "bad",
                    "timeMs": 1,
                    "memoryBytes": 1,
                }
            ],
            "metrics": {"maxTimeLabel": "1 ms", "maxMemoryLabel": "1 B"},
            "firstFailedCase": "001",
        }
        artifact = "x" * 12040
        wrong_payload = {
            "previewLimit": 12000,
            "input": artifact,
            "expected": "ok\n",
            "actual": artifact,
            "diff": artifact,
            "truncation": {
                "input": {"truncated": True, "omittedChars": 40},
                "expected": {"truncated": False, "omittedChars": 0},
                "actual": {"truncated": True, "omittedChars": 40},
                "diff": {"truncated": True, "omittedChars": 40},
            },
        }

        with isolated_runtime("alj-judge-web-truncated-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                jobs: dict[str, dict] = {}
                route_jobs_list(page, jobs)
                page.route(
                    "**/api/cases/jobs",
                    lambda route: (
                        jobs.setdefault(
                            "cases-truncated",
                            completed_job(
                                "cases-truncated",
                                "judge-cases-compile",
                                "Check Cases · 06",
                                valid_compile,
                            ),
                        ),
                        route.fulfill(json=jobs["cases-truncated"]),
                    ),
                )
                page.route(
                    "**/api/run/jobs",
                    lambda route: (
                        jobs.setdefault(
                            "run-big-job",
                            completed_job(
                                "run-big-job",
                                "judge-run",
                                "Run Tests · 06",
                                run_result,
                            ),
                        ),
                        route.fulfill(json=jobs["run-big-job"]),
                    ),
                )
                page.route(
                    "**/api/runs/run-big/wrong/001",
                    lambda route: route.fulfill(json=wrong_payload),
                )
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                page.locator("#textModeButton").click()
                page.locator("#filenameInput").fill("wrong.py")
                page.locator("#sourceTextInput").fill(source)
                page.locator("#runButton").click()
                wait_for_text(page, "#statusBadge", "wrong answer")
                page.get_by_role("button", name="Actual").click()
                wait_for_text(page, "#artifactNotice", "긴 데이터")
                wait_for_text(page, "#artifactNotice", "생략된 문자")
                self.assertTrue(
                    page.locator("#artifactOutput").evaluate(
                        "node => node.classList.contains('collapsed')"
                    )
                )
                page.locator("#artifactExpandButton").click()
                self.assertFalse(
                    page.locator("#artifactOutput").evaluate(
                        "node => node.classList.contains('collapsed')"
                    )
                )
                self.assert_no_browser_errors()

    def test_mobile_text_run_workflow_keeps_result_visible(self) -> None:
        source = (ROOT / "tests" / "fixtures" / "accepted.py").read_text(encoding="utf-8")
        with isolated_runtime("alj-judge-web-mobile-run-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url, width=390, height=844)
                stub_samples(page)
                page.goto(server.url)
                page.locator("#runButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#runProfileSelect").select_option("sample")
                page.locator("#textModeButton").click()
                page.locator("#filenameInput").fill("main.py")
                page.locator("#sourceTextInput").fill(source)
                assert_visible_in_viewport(self, page.locator("#runButton"))
                page.locator("#runButton").click()
                wait_for_text(page, "#statusBadge", "accepted", timeout=120_000)
                page.locator("#resultSummary").scroll_into_view_if_needed()
                assert_visible_in_viewport(self, page.locator("#resultSummary"))
                self.assert_no_browser_errors()

    def test_judge_web_viewports_keep_core_controls_usable(self) -> None:
        with isolated_runtime("alj-judge-web-view-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                for width, height in [(1440, 900), (900, 900), (390, 844)]:
                    page = self.new_page(server.url, width=width, height=height)
                    page.goto(server.url)
                    page.locator("#runButton").wait_for(state="visible")
                    page.wait_for_function(
                        """() => {
                            const button = document.querySelector("#cacheManageButton");
                            return button && !button.disabled;
                        }"""
                    )
                    assert_visible_in_viewport(self, page.locator("#runButton"))
                    assert_visible_in_viewport(self, page.locator("#problemSelect"))
                    assert_visible_in_viewport(self, page.locator("#runProfileSelect"))
                    assert_visible_in_viewport(self, page.locator("#sourceReadiness"))
                    page.locator(".advanced-run-options > summary").click()
                    assert_visible_in_viewport(self, page.locator(".advanced-actions"))
                    self.assertTrue(
                        page.evaluate(
                            "() => document.documentElement.scrollWidth <= window.innerWidth + 1"
                        )
                    )
                    page.locator(".advanced-run-options > summary").click()
                    page.locator("#cacheManageButton").click()
                    assert_visible_in_viewport(self, page.locator("#cacheModal"))
                    page.keyboard.press("Escape")
                    if width >= 900:
                        assert_no_overlap(
                            self,
                            page.locator(".run-panel"),
                            page.locator(".sample-panel"),
                        )
                    self.assert_no_browser_errors()
