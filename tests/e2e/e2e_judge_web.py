"""judge 웹 화면을 브라우저에서 조작하며 실행, 생성, 패키지 설치, 반응형 화면 계약을 검증하는 종단 간 테스트 모듈입니다."""

from __future__ import annotations

import re

from judge.web import services
from judge.web.app import create_app
from tests.e2e.helpers import (
    ROOT,
    BrowserE2ETestCase,
    assert_no_overlap,
    assert_visible_in_viewport,
    create_minimal_pack,
    create_runnable_minimal_pack,
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
    """브라우저 테스트가 샘플 생성 백엔드 없이 문제 샘플 목록을 렌더링하도록 응답을 대체합니다.

    Args:
        page (Any): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
    """
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
    """브라우저 테스트에서 작업 목록 요청을 가로채 고정된 API 응답을 제공하도록 설정합니다.

    Args:
        page (Any): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        jobs (dict[str, dict]): 브라우저 라우팅에 사용할 작업 목록 응답 데이터입니다.
    """
    page.route(re.compile(r"/api/jobs(?:\?.*)?$"), lambda route: route.fulfill(json={"jobs": list(jobs.values())}))


def wait_for_captured_body(page, captured: dict[str, str], *, timeout_ms: int = 5000) -> str:
    for _ in range(max(1, timeout_ms // 100)):
        if captured.get("body"):
            return captured["body"]
        page.wait_for_timeout(100)
    return captured.get("body", "")


def completed_job(
    job_id: str,
    kind: str,
    title: str,
    result: dict,
    *,
    problem_id: str = "06",
    target: dict | None = None,
) -> dict:
    """화면이 완료된 작업을 렌더링할 수 있도록 작업 작업 응답 페이로드를 구성합니다.

    Args:
        job_id (str): 조회하거나 구성할 백그라운드 작업 식별자입니다.
        kind (str): 작업 큐 화면에서 구분할 작업 종류입니다.
        title (str): 작업 목록이나 문제 메타데이터에 표시할 제목입니다.
        result (dict): 완료된 작업 응답에 포함할 결과 페이로드입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
        target (dict | None): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.

    Returns:
        dict: 완료된 judge 웹 작업을 나타내는 작업 큐 응답 객체입니다.
    """
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


def seed_judge_web_problem(runtime, problem_id: str = "e2e-cold") -> str:
    """Judge 웹 테스트가 공식 문제 fixture 없이도 실행 가능한 문제를 갖도록 설치합니다."""
    seed_pack = create_runnable_minimal_pack(
        runtime / f"{problem_id}.aljpack",
        pack_id=f"{problem_id}-pack",
        problem_id=problem_id,
    )
    with temporary_env(judge_env(runtime)):
        services.install_problem_pack(str(seed_pack))
    return problem_id


class JudgeWebE2ETest(BrowserE2ETestCase):
    """채점기 웹 종단 간 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_judge_cold_start_sample_run_first_click_succeeds_with_seed_pack(self) -> None:
        """공식 문제 06 없이 새 런타임의 첫 예제 채점이 실제 큐 경로에서 성공해야 합니다."""
        source = "print(1)\n"
        with isolated_runtime("alj-judge-web-cold-start-e2e-") as (_directory, runtime):
            problem_id = seed_judge_web_problem(runtime)
            with temporary_env(judge_env(runtime)):
                app = create_app()
            with temporary_env(judge_env(runtime)), run_app(app) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.wait_for_function(
                    """problemId => Array.from(
                        document.querySelector("#problemSelect")?.options || []
                    ).some((option) => option.value === problemId)""",
                    arg=problem_id,
                )
                page.locator("#problemSelect").select_option(problem_id)
                page.locator("#filenameInput").fill("answer.py")
                page.locator("#sourceTextInput").fill(source)
                page.wait_for_function(
                    """() => {
                        const button = document.querySelector("#sampleRunButton");
                        return button && !button.disabled;
                    }"""
                )

                page.locator("#sampleRunButton").click()
                wait_for_text(page, "#statusBadge", "맞았습니다", timeout=120_000)
                wait_for_text(page, "#jobsButton", "작업 센터", timeout=120_000)
                page.wait_for_function(
                    """async () => {
                        const response = await fetch("/api/jobs");
                        const payload = await response.json();
                        const jobs = payload.jobs || [];
                        return jobs.some((job) => job.kind === "judge-run" && job.status === "succeeded")
                            && !jobs.some((job) => job.status === "failed");
                    }""",
                    timeout=120_000,
                )
                self.assert_no_browser_errors()

    def test_selected_problem_is_restored_after_reload_in_browser(self) -> None:
        """선택된 문제 복원 이후 새로고침 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("persist")
                wait_for_text(page, "#problemList", "Persisted")
                page.wait_for_function(
                    "() => localStorage.getItem('alj:selected-problem:v1') === 'persist'"
                )
                page.wait_for_function(
                    "() => new URL(window.location.href).searchParams.get('problem') === 'persist'"
                )

                page.reload()
                page.locator("#sampleRunButton").wait_for(state="visible")
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
        """문제 폴더 드래그 드롭 갱신 문제 메타데이터 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
            """갱신 폴더 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
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
                page.locator("#sampleRunButton").wait_for(state="visible")
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
                wait_for_text(page, "#toastHost", "alpha 문제를 Graph 폴더로 옮겼습니다.")
                self.assertEqual(captured, {"problemId": "alpha", "folder": "Graph"})
                self.assertEqual(
                    page.locator('.problem-folder-group[data-folder="Graph"] .list-item').count(),
                    2,
                )

                page.locator("#problemFolderInput").fill("Dynamic")
                page.locator("#problemFolderSaveButton").click()
                wait_for_text(page, "#toastHost", "폴더 생성: Dynamic")
                page.evaluate(
                    """() => {
                        const source = document.querySelector('[data-problem-id="alpha"]');
                        const target = [...document.querySelectorAll('.problem-folder-group')]
                          .find((group) => group.dataset.folder === 'Dynamic');
                        const dataTransfer = new DataTransfer();
                        source.dispatchEvent(new DragEvent('dragstart', {
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
                wait_for_text(page, "#toastHost", "alpha 문제를 Dynamic 폴더로 옮겼습니다.")
                self.assertEqual(captured, {"problemId": "alpha", "folder": "Dynamic"})
                self.assert_no_browser_errors()

    def test_problem_folder_create_collapse_and_delete_confirmation_in_browser(self) -> None:
        """폴더 생성, 접기, 빈 폴더 삭제, 문제 포함 폴더 삭제 확인창을 브라우저에서 검증합니다."""
        problems = [
            {
                "problemId": "alpha",
                "title": "Alpha",
                "version": 1,
                "defaultProfile": "full",
                "profiles": ["sample"],
                "folder": "",
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
        folders = [
            {"folder": "", "label": "미분류", "problemCount": 1},
            {"folder": "Graph", "label": "Graph", "problemCount": 1},
        ]
        dialogs: list[str] = []

        def folders_route(route):
            """브라우저 폴더 관리 테스트용 폴더 API 응답을 제공합니다."""
            request = route.request
            if request.method == "GET":
                route.fulfill(json=folders)
                return
            body = request.post_data_json
            if request.method == "POST":
                folder = body["folder"]
                folders.append({"folder": folder, "label": folder, "problemCount": 0})
                route.fulfill(json={"folder": folder, "folders": folders})
                return
            if request.method == "DELETE":
                folder = body["folder"]
                folders[:] = [item for item in folders if item["folder"] != folder]
                if body.get("confirm_delete_problems"):
                    problems[:] = [problem for problem in problems if problem["folder"] != folder]
                route.fulfill(
                    json={
                        "deleted": True,
                        "folder": folder,
                        "deletedProblems": ["beta"] if folder == "Graph" else [],
                        "folders": folders,
                    }
                )
                return
            route.fulfill(status=405, json={"detail": "method not allowed"})

        with isolated_runtime("alj-judge-web-folder-delete-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                page.route("**/api/problems", lambda route: route.fulfill(json=problems))
                page.route("**/api/folders", folders_route)
                page.route(
                    "**/api/problems/*/samples**",
                    lambda route: route.fulfill(
                        json={"profile": "sample", "caseCount": 0, "label": "folder", "cases": []}
                    ),
                )
                page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")

                page.locator("#problemFolderInput").fill("Empty")
                page.locator("#problemFolderSaveButton").click()
                wait_for_text(page, "#problemList", "Empty")
                self.assertEqual(dialogs, [])

                page.locator('[data-folder-toggle="Graph"]').click()
                self.assertTrue(
                    page.locator('.problem-folder-group[data-folder="Graph"] .problem-folder-items')
                    .evaluate("node => node.classList.contains('hidden')")
                )
                page.reload()
                page.locator("#sampleRunButton").wait_for(state="visible")
                self.assertTrue(
                    page.locator('.problem-folder-group[data-folder="Graph"] .problem-folder-items')
                    .evaluate("node => node.classList.contains('hidden')")
                )

                page.locator('[data-folder-delete="Empty"]').click()
                page.wait_for_function(
                    "() => !document.querySelector('[data-folder-delete=\"Empty\"]')"
                )
                self.assertEqual(dialogs, [])

                page.locator('[data-folder-delete="Graph"]').click()
                page.wait_for_function(
                    "() => !document.querySelector('[data-problem-id=\"beta\"]')"
                )
                self.assertTrue(any("폴더 내 문제들이 모두 삭제됩니다" in text for text in dialogs))
                self.assert_no_browser_errors()

    def test_submission_language_buttons_jobs_and_case_results_in_browser(self) -> None:
        """제출 언어 자동 변경, 전체 채점 버튼, 제출 기록 페이지네이션, testcase 결과 렌더링을 검증합니다."""
        jobs: dict[str, dict] = {}
        captured_run_request = {"body": ""}
        base_result = {
            "runId": "run-newest",
            "problemId": "06",
            "profile": "full",
            "language": "C++",
            "status": "wrong_answer",
            "caseCount": 2,
            "cases": [
                {"case": "001", "status": "ok", "timeMs": 1, "memoryBytes": 1024},
                {
                    "case": "002",
                    "status": "wrong_answer",
                    "message": "expected 2, got 1",
                    "timeMs": 2,
                    "memoryBytes": 2048,
                },
            ],
            "metrics": {"maxTimeLabel": "2 ms", "maxMemoryLabel": "2 KiB"},
            "firstFailedCase": None,
        }
        for index in range(6):
            job_id = f"run-{index}"
            result = dict(base_result)
            result["runId"] = job_id
            jobs[job_id] = completed_job(
                job_id,
                "judge-run",
                f"채점 · {index}",
                result,
                target={"problemId": "06", "profile": "full", "source": f"main-{index}.cpp"},
            )
            jobs[job_id]["queuedAt"] = f"2026-06-01T00:00:0{index}+00:00"

        def create_cases_job(route):
            job = completed_job(
                "cases-language",
                "judge-cases-compile",
                "Check Cases · 06",
                VALID_CASES_COMPILE,
            )
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        def create_run_job(route):
            captured_run_request["body"] = route.request.post_data or ""
            newest = jobs["run-5"]
            route.fulfill(json=newest)

        with isolated_runtime("alj-judge-web-result-list-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                route_jobs_list(page, jobs)
                page.route("**/api/cases/jobs", create_cases_job)
                page.route("**/api/run/jobs", create_run_job)
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#filenameInput").fill("main.cpp")
                page.wait_for_function("() => document.querySelector('#languageHint')?.value === 'cpp'")
                wait_for_text(page, "#languageBadge", "C++")
                page.locator("#sourceTextInput").fill("int main(){return 0;}\n")
                page.locator("#fullRunButton").click()

                page.wait_for_function(
                    "() => document.querySelector('#jobsPageLabel')?.textContent === '1 / 2'"
                )
                wait_for_text(page, "#jobsPanel", "채점 · 5")
                run_body = wait_for_captured_body(page, captured_run_request)
                self.assertIn('name="profile"', run_body)
                self.assertIn("full", run_body)
                self.assertNotIn("Active", page.locator("#jobsPanel").inner_text())
                self.assertNotIn("Done", page.locator("#jobsPanel").inner_text())
                self.assertNotIn("Failed", page.locator("#jobsPanel").inner_text())

                page.locator("#jobsNextButton").click()
                wait_for_text(page, "#jobsPanel", "채점 · 0")
                page.locator("#jobsPrevButton").click()
                page.locator('[data-job-result="run-5"]').click()
                wait_for_text(page, "#resultModal", "테스트케이스 결과")
                wait_for_text(page, "#resultModal", "맞음")
                wait_for_text(page, "#resultModal", "틀림")
                wait_for_text(page, "#resultModal", "expected 2, got 1")
                self.assert_no_browser_errors()

    def test_pasted_source_runs_and_updates_history_in_browser(self) -> None:
        """붙여넣은 소스 실행 및 갱신 기록 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        source = (ROOT / "tests" / "fixtures" / "accepted.py").read_text(encoding="utf-8")
        with isolated_runtime("alj-judge-web-e2e-") as (_directory, runtime):
            env = judge_env(runtime)
            with temporary_env(env), run_app(create_app()) as server:
                page = self.new_page(server.url)
                page.goto(server.url)

                page.locator("#sampleRunButton").wait_for(state="visible")
                page.wait_for_function(
                    """() => document.querySelector("#problemSelect")?.options.length > 0"""
                )
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#sourceTextInput").wait_for(state="visible")
                page.locator("#filenameInput").fill("main.py")
                page.locator("#sourceTextInput").fill(source)

                wait_for_text(page, "#sourceReadiness", "main.py 준비됨")
                page.locator("#fullRunButton").click()
                wait_for_text(page, "#statusBadge", "맞았습니다", timeout=120_000)
                wait_for_text(page, "#resultSummary", "채점 완료", timeout=120_000)
                wait_for_text(page, "#sourceHistoryList", "main.py", timeout=120_000)
                wait_for_text(page, "#sourceHistoryList", "accepted", timeout=120_000)
                wait_for_text(page, "#sampleCases", "Input")

                page.locator("#cacheManageButton").click()
                page.on("dialog", lambda dialog: dialog.accept())
                page.locator("#cacheClearAllButton").click()
                wait_for_text(page, "#cacheOutput", "삭제했습니다", timeout=30_000)
                wait_for_text(page, "#sourceHistoryList", "캐시 소스가 없습니다")
                page.keyboard.press("Escape")

                page.locator("#themeToggleButton").click()
                theme = page.evaluate("() => document.documentElement.dataset.theme")
                page.reload()
                page.locator("#sampleRunButton").wait_for(state="visible")
                reloaded_theme = page.evaluate("() => document.documentElement.dataset.theme")
                self.assertEqual(reloaded_theme, theme)
                self.assert_no_browser_errors()

    def test_uploaded_source_history_load_delete_and_cache_modal_in_browser(self) -> None:
        """업로드된 소스 기록 로드 삭제 및 캐시 모달 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        source_path = ROOT / "tests" / "fixtures" / "accepted.py"
        source_text = source_path.read_text(encoding="utf-8")
        with isolated_runtime("alj-judge-web-e2e-") as (_directory, runtime):
            seed_pack = create_minimal_pack(runtime / "seed-06.aljpack", "seed-06", "06")
            with temporary_env(judge_env(runtime)):
                services.install_problem_pack(str(seed_pack))
                app = create_app()
            with temporary_env(judge_env(runtime)), run_app(app) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                jobs: dict[str, dict] = {}
                sources: dict[str, dict] = {}
                route_jobs_list(page, jobs)
                accepted_result = {
                    "runId": "run-source-history",
                    "problemId": "06",
                    "profile": "full",
                    "language": "python",
                    "status": "accepted",
                    "cases": [{"case": "001", "status": "ok", "timeMs": 1, "memoryBytes": 1}],
                    "metrics": {"maxTimeLabel": "1 ms", "maxMemoryLabel": "1 B"},
                    "firstFailedCase": None,
                }
                page.route(
                    "**/api/cases/jobs",
                    lambda route: (
                        jobs.setdefault(
                            "cases-source-history",
                            completed_job(
                                "cases-source-history",
                                "judge-cases-compile",
                                "Check Cases · 06",
                                VALID_CASES_COMPILE,
                            ),
                        ),
                        route.fulfill(json=jobs["cases-source-history"]),
                    ),
                )

                def create_source_history_run(route):
                    sources["src-1"] = {
                        "sourceId": "src-1",
                        "problemId": "06",
                        "filename": "accepted.py",
                        "language": "python",
                        "sizeLabel": "1 KiB",
                        "savedAt": 1,
                        "lastRun": {"status": "accepted"},
                    }
                    job = completed_job(
                        "run-source-history",
                        "judge-run",
                        "채점 · 06",
                        {**accepted_result, "sourceId": "src-1"},
                        target={"problemId": "06", "profile": "full", "source": "accepted.py"},
                    )
                    jobs[job["jobId"]] = job
                    route.fulfill(json=job)

                page.route("**/api/run/jobs", create_source_history_run)
                page.route(
                    re.compile(r"/api/sources(?:\?.*)?$"),
                    lambda route: route.fulfill(json={"sources": list(sources.values())}),
                )

                def source_detail(route):
                    if route.request.method == "DELETE":
                        sources.pop("src-1", None)
                        route.fulfill(json={"deleted": True, "sourceId": "src-1"})
                        return
                    route.fulfill(
                        json={
                            **sources["src-1"],
                            "sourceText": source_text,
                            "lastRunResult": {**accepted_result, "sourceId": "src-1"},
                        }
                    )

                page.route("**/api/sources/src-1", source_detail)
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.wait_for_function(
                    """() => document.querySelector("#problemSelect")?.options.length > 0"""
                )
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#sourceFileInput").set_input_files(str(source_path))
                wait_for_text(page, "#sourceReadiness", "accepted.py 준비됨")
                page.locator("#fullRunButton").click()
                wait_for_text(page, "#statusBadge", "맞았습니다", timeout=120_000)
                wait_for_text(page, "#sourceHistoryList", "accepted.py", timeout=120_000)

                page.reload()
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.wait_for_function(
                    """() => document.querySelector("#problemSelect")?.options.length > 0"""
                )
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
                wait_for_text(page, "#sourceHistoryList", "accepted.py", timeout=120_000)
                page.get_by_role("button", name="코드 사용").first.click()
                wait_for_text(page, "#sourceReadiness", "accepted.py 준비됨")
                page.wait_for_function(
                    """() => document
                        .querySelector("#sourceTextInput")
                        ?.value.includes("def main")"""
                )
                wait_for_text(page, "#sampleCases", "Input")
                self.assertIn("def main", page.locator("#sourceTextInput").input_value())
                wait_for_text(page, "#resultSummary", "채점 완료")
                wait_for_text(page, "#resultMeta", "06")

                page.on("dialog", lambda dialog: dialog.accept())
                page.locator(".source-history-actions .danger").first.click()
                wait_for_text(page, "#toastHost", "캐시 소스 삭제됨")
                wait_for_text(page, "#sourceHistoryList", "캐시 소스가 없습니다")

                page.locator("#cacheManageButton").click()
                page.locator("#cachePreviewButton").click()
                wait_for_text(page, "#cacheOutput", "삭제할 예정")
                page.locator("#cacheClearRunsButton").click()
                wait_for_text(page, "#cacheOutput", "삭제했습니다")
                self.assert_no_browser_errors()

    def test_wrong_answer_artifacts_and_pack_install_ui_in_browser(self) -> None:
        """오답 답안 산출물 및 패키지 설치 화면 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        wrong_source = "print(42)\n"
        valid_compile = {
            "valid": True,
            "path": "/tmp/cases.yml",
            "profiles": [{"name": "full", "caseCount": 1, "cases": []}],
            "diagnostics": [],
        }
        run_result = {
            "runId": "run-wrong",
            "problemId": "06",
            "profile": "full",
            "language": "python",
            "status": "wrong_answer",
            "cases": [
                {
                    "case": "001",
                    "status": "wrong_answer",
                    "message": "expected 1, got 42",
                    "timeMs": 1,
                    "memoryBytes": 1,
                }
            ],
            "metrics": {"maxTimeLabel": "1 ms", "maxMemoryLabel": "1 B"},
            "firstFailedCase": "001",
        }
        wrong_payload = {
            "previewLimit": 12000,
            "input": "1\n",
            "expected": "1\n",
            "actual": "42\n",
            "diff": "-1\n+42\n",
            "truncation": {
                "input": {"truncated": False, "omittedChars": 0},
                "expected": {"truncated": False, "omittedChars": 0},
                "actual": {"truncated": False, "omittedChars": 0},
                "diff": {"truncated": False, "omittedChars": 0},
            },
        }
        with isolated_runtime("alj-judge-web-e2e-") as (_directory, runtime):
            pack_path = create_minimal_pack(runtime / "e2e-pack.aljpack")
            seed_pack = create_minimal_pack(runtime / "seed-06.aljpack", "seed-06", "06")
            with temporary_env(judge_env(runtime)):
                services.install_problem_pack(str(seed_pack))
                app = create_app()
            with temporary_env(judge_env(runtime)), run_app(app) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                jobs: dict[str, dict] = {}
                route_jobs_list(page, jobs)
                page.route(
                    "**/api/cases/jobs",
                    lambda route: (
                        jobs.setdefault(
                            "cases-wrong",
                            completed_job(
                                "cases-wrong",
                                "judge-cases-compile",
                                "Check Cases · 06",
                                valid_compile,
                            ),
                        ),
                        route.fulfill(json=jobs["cases-wrong"]),
                    ),
                )
                page.route(
                    "**/api/run/jobs",
                    lambda route: (
                        jobs.setdefault(
                            "run-wrong-job",
                            completed_job("run-wrong-job", "judge-run", "채점 · 06", run_result),
                        ),
                        route.fulfill(json=jobs["run-wrong-job"]),
                    ),
                )
                page.route(
                    "**/api/runs/run-wrong/wrong/001",
                    lambda route: route.fulfill(json=wrong_payload),
                )
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.wait_for_function(
                    """() => document.querySelector("#problemSelect")?.options.length > 0"""
                )
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#sourceTextInput").wait_for(state="visible")
                page.locator("#filenameInput").fill("wrong.py")
                page.locator("#sourceTextInput").fill(wrong_source)
                wait_for_text(page, "#sourceReadiness", "wrong.py 준비됨")
                page.locator("#fullRunButton").click()
                wait_for_text(page, "#statusBadge", "오답", timeout=120_000)
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

                page.unroute(re.compile(r"/api/jobs(?:\?.*)?$"))
                page.locator("#addProblemButton").click()
                page.locator("#packFileInput").set_input_files(str(pack_path))
                page.locator("#uploadPackButton").click()
                wait_for_text(page, "#packStatus", "문제 팩 설치 완료", timeout=30_000)
                wait_for_text(page, "#problemList", "e2e", timeout=30_000)
                self.assert_no_browser_errors()

    def test_generate_stream_success_updates_progress_in_browser(self) -> None:
        """생성 스트림 성공 갱신 진행 상황 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-web-generate-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator(".advanced-run-options > summary").click()
                page.locator("#forceGenerateInput").check()
                page.locator("#generateButton").click()
                wait_for_text(page, "#statusBadge", "생성 완료", timeout=120_000)
                wait_for_text(page, "#dataStatusValue", "생성 완료", timeout=120_000)
                wait_for_text(page, "#resultSummary", "테스트 데이터 준비 완료", timeout=120_000)
                wait_for_text(page, "#generationProgress", "/")
                self.assert_no_browser_errors()

    def test_run_job_queue_is_visible_and_cancelable_in_browser(self) -> None:
        """실행 작업 큐 표시 및 취소 가능 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        source = "print(1)\n"
        jobs = {}

        def listed_jobs():
            """목록화 작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Returns:
                Any: 호출자가 다음 검증 단계에서 사용할 결과 값입니다.
            """
            return {"jobs": list(jobs.values())}

        def create_cases_job(route):
            """케이스 작업 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
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
            """실행 작업 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            job = {
                "jobId": "run-1",
                "kind": "judge-run",
                "title": "채점 · 06",
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
            """취소 작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            job = jobs["run-1"]
            job["status"] = "cancelled"
            job["cancelRequested"] = True
            job["lastLog"] = "취소를 요청했습니다."
            route.fulfill(json=job)

        with isolated_runtime("alj-judge-web-job-cancel-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                page.route("**/api/cases/jobs", create_cases_job)
                page.route("**/api/run/jobs", create_run_job)
                page.route(re.compile(r"/api/jobs(?:\?.*)?$"), lambda route: route.fulfill(json=listed_jobs()))
                page.route("**/api/jobs/run-1/cancel", cancel_job)
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#sourceTextInput").wait_for(state="visible")
                page.locator("#filenameInput").fill("main.py")
                page.locator("#sourceTextInput").fill(source)
                page.locator("#sampleRunButton").click()
                wait_for_text(page, "#jobsPanel", "채점")
                wait_for_text(page, "#jobsPanel", "실행 중")
                self.assertFalse(page.locator("#sourceTextInput").is_disabled())
                page.locator('[data-job-cancel="run-1"]').click()
                page.locator("#jobsPanel").wait_for(state="visible")
                wait_for_text(page, "#jobsPanel", "취소됨")
                self.assert_no_browser_errors()

    def test_judge_job_center_lists_all_job_kinds_and_failure_details_in_browser(self) -> None:
        """작업 센터가 채점 외 작업과 domain 실패 상세를 필터별로 노출해야 합니다."""
        run_result = {
            "runId": "run-attention",
            "problemId": "e2e",
            "profile": "sample",
            "language": "python",
            "status": "wrong_answer",
            "cases": [
                {
                    "case": "001",
                    "status": "wrong_answer",
                    "message": "expected 1, got 2",
                    "timeMs": 1,
                    "memoryBytes": 1,
                }
            ],
            "metrics": {"maxTimeLabel": "1 ms", "maxMemoryLabel": "1 B"},
            "firstFailedCase": "001",
            "failureStage": "solutions",
            "failureStageLabel": "채점 결과",
            "failureDetails": [
                {
                    "label": "오답",
                    "target": "case 001",
                    "message": "expected 1, got 2",
                    "status": "wrong_answer",
                    "profile": "sample",
                }
            ],
        }
        cases_result = {
            "valid": False,
            "path": "/tmp/cases.yml",
            "profiles": [],
            "diagnostics": [
                {
                    "severity": "error",
                    "path": "problems/e2e/generator/cases.yml",
                    "line": 7,
                    "profile": "sample",
                    "location": "profiles.sample.cases[0]",
                    "message": "forced cases compile failure",
                }
            ],
            "failureStage": "cases",
            "failureStageLabel": "cases.yml 검사",
        }
        jobs = {
            "run-attention": {
                **completed_job(
                    "run-attention",
                    "judge-run",
                    "채점 · e2e",
                    run_result,
                    problem_id="e2e",
                    target={"problemId": "e2e", "profile": "sample", "source": "answer.py"},
                ),
                "outcome": "failed",
                "failureStage": "solutions",
                "failureStageLabel": "채점 결과",
                "failureDetails": run_result["failureDetails"],
                "queuedAt": "2026-06-29T00:00:05+00:00",
            },
            "cases-attention": {
                **completed_job(
                    "cases-attention",
                    "judge-cases-compile",
                    "cases.yml 검사 · e2e",
                    cases_result,
                    problem_id="e2e",
                    target={"problemId": "e2e", "profile": "sample"},
                ),
                "outcome": "failed",
                "failureStage": "cases",
                "failureStageLabel": "cases.yml 검사",
                "queuedAt": "2026-06-29T00:00:04+00:00",
            },
            "generate-attention": {
                **completed_job(
                    "generate-attention",
                    "judge-generate",
                    "데이터 생성 · e2e",
                    {},
                    problem_id="e2e",
                    target={"problemId": "e2e", "profile": "full"},
                ),
                "status": "failed",
                "outcome": "failed",
                "failureStage": "validation",
                "failureStageLabel": "데이터 생성",
                "error": "generator crashed on cold cache",
                "lastLog": "generator crashed on cold cache",
                "queuedAt": "2026-06-29T00:00:03+00:00",
            },
            "pack-ok": {
                **completed_job(
                    "pack-ok",
                    "judge-pack-upload",
                    "문제 팩 설치 · seed.aljpack",
                    {"packId": "seed", "label": "seed.aljpack"},
                    problem_id="__packs__",
                    target={"filename": "seed.aljpack"},
                ),
                "queuedAt": "2026-06-29T00:00:02+00:00",
            },
            "run-active": {
                "jobId": "run-active",
                "kind": "judge-run",
                "title": "채점 · active",
                "problemId": "active",
                "status": "running",
                "cancelSupported": True,
                "target": {"problemId": "active", "profile": "sample", "source": "main.py"},
                "progress": {"message": "Running case 001.", "current": 1, "total": 2},
                "lastLog": "Running case 001.",
                "logs": [{"message": "Running case 001."}],
                "result": None,
                "queuedAt": "2026-06-29T00:00:01+00:00",
            },
        }

        with isolated_runtime("alj-judge-web-job-center-all-kinds-e2e-") as (
            _directory,
            runtime,
        ):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                route_jobs_list(page, jobs)
                page.goto(server.url)
                wait_for_text(page, "#jobsButton", "주의 3")
                page.locator("#jobsButton").click()
                wait_for_text(page, "#jobsPanel", "전체 5개")
                wait_for_text(page, "#jobsPanel", "채점 · e2e")
                wait_for_text(page, "#jobsPanel", "cases.yml 검사 · e2e")
                wait_for_text(page, "#jobsPanel", "데이터 생성 · e2e")
                wait_for_text(page, "#jobsPanel", "문제 팩 설치 · seed.aljpack")

                page.locator('[data-jobs-filter="attention"]').click()
                wait_for_text(page, "#jobsList", "오답")
                wait_for_text(page, "#jobsList", "case 001")
                wait_for_text(page, "#jobsList", "expected 1, got 2")
                wait_for_text(page, "#jobsList", "forced cases compile failure")
                wait_for_text(page, "#jobsList", "generator crashed on cold cache")
                self.assertNotIn("문제 팩 설치 · seed.aljpack", page.locator("#jobsList").inner_text())

                page.locator('[data-jobs-filter="maintenance"]').click()
                wait_for_text(page, "#jobsList", "cases.yml 검사 · e2e")
                wait_for_text(page, "#jobsList", "데이터 생성 · e2e")
                wait_for_text(page, "#jobsList", "문제 팩 설치 · seed.aljpack")
                self.assertNotIn("채점 · e2e", page.locator("#jobsList").inner_text())

                page.locator('[data-jobs-filter="runs"]').click()
                wait_for_text(page, "#jobsList", "채점 · e2e")
                wait_for_text(page, "#jobsList", "채점 · active")
                self.assertNotIn("데이터 생성 · e2e", page.locator("#jobsList").inner_text())
                self.assert_no_browser_errors()

    def test_cases_compile_failure_blocks_run_stream_in_browser(self) -> None:
        """케이스 컴파일 실패 차단 실행 스트림 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
                    """잘못된 케이스 작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                    Args:
                        route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
                    """
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
                    """실패 조건 실행 작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                    Args:
                        route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
                    """
                    run_stream_called["value"] = True
                    route.fulfill(
                        status=500,
                        content_type="application/json",
                        body='{"detail":"run job should not be called"}',
                    )

                page.route("**/api/run/jobs", fail_if_run_job)
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#sourceTextInput").wait_for(state="visible")
                page.locator("#filenameInput").fill("main.py")
                page.locator("#sourceTextInput").fill(source)
                page.locator("#sampleRunButton").click()
                wait_for_text(page, "#statusBadge", "Cases 오류")
                wait_for_text(page, "#resultSummary", "forced compile failure")
                self.assertFalse(run_stream_called["value"])
                self.assert_no_browser_errors()

    def test_run_stream_error_event_is_visible_in_browser(self) -> None:
        """실행 스트림 오류 이벤트 표시 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        captured_run_request = {"body": ""}
        jobs: dict[str, dict] = {}

        def run_job_handler(route):
            """작업 처리기 흐름을 격리된 환경에서 실행해 종료 코드와 출력을 검증할 수 있게 합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            captured_run_request["body"] = route.request.post_data or ""
            job = completed_job(
                "run-error",
                "judge-run",
                "채점 · 06",
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
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#sourceTextInput").wait_for(state="visible")
                page.locator("#filenameInput").fill("main.cpp")
                page.locator("#sourceTextInput").fill("int main( { return 0; }\n")

                page.locator("#sampleRunButton").click()
                wait_for_text(page, "#statusBadge", "오류")
                wait_for_text(page, "#resultSummary", "compile failed: main.cpp")
                run_body = wait_for_captured_body(page, captured_run_request)
                self.assertIn('name="profile"', run_body)
                self.assertIn("sample", run_body)
                self.assert_no_browser_errors()

    def test_runtime_and_time_limit_result_states_render_in_browser(self) -> None:
        """런타임 및 시간 한도 결과 상태 렌더링 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        scenarios = [
            ("runtime_error", "Runtime crashed"),
            ("time_limit", "Time limit exceeded"),
        ]
        for status, message in scenarios:
            with self.subTest(status=status):
                jobs: dict[str, dict] = {}

                def make_run_job_handler(status_value, message_value, job_map=jobs):
                    """실행 작업 처리기 테스트가 후속 API 호출이나 명령 실행에 사용할 임시 리소스를 준비합니다.

                    Args:
                        status_value (Any): 상태 값 값을 지정하는 인자입니다.
                        message_value (Any): 작업 스트림 응답에 포함할 메시지 값입니다.
                        job_map (Any): 작업 식별자별 상태를 보관하는 사전입니다.

                    Returns:
                        Any: 호출자가 다음 검증 단계에서 사용할 결과 값입니다.
                    """

                    def fulfill_run_job(route):
                        """응답 완료 실행 작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                        Args:
                            route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
                        """
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
                            "채점 · 06",
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
                            """응답 완료 케이스 작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                            Args:
                                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
                                _request (Any): 라우팅 시그니처를 맞추기 위해 받지만 본문에서는 사용하지 않는 요청 객체입니다.
                                job_map (Any): 작업 식별자별 상태를 보관하는 사전입니다.
                            """
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
                        page.locator("#sampleRunButton").wait_for(state="visible")
                        page.locator("#problemSelect").select_option("06")
                        page.locator("#sourceTextInput").wait_for(state="visible")
                        page.locator("#filenameInput").fill("main.py")
                        page.locator("#sourceTextInput").fill("raise SystemExit(1)\n")

                        page.locator("#sampleRunButton").click()
                        label = {
                            "runtime_error": "런타임 오류",
                            "time_limit": "시간 초과",
                        }[status]
                        wait_for_text(page, "#statusBadge", label)
                        wait_for_text(page, "#judgeStatusValue", label)
                        wait_for_text(page, "#resultSummary", label)
                        self.assert_no_browser_errors()

    def test_official_pack_download_ui_uses_repository_asset_and_ref(self) -> None:
        """공식 패키지 다운로드 화면 사용 저장소 자산 및 참조 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        captured: dict[str, object] = {}
        jobs: dict[str, dict] = {}

        def capture_download(route):
            """캡처 다운로드 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
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
                page.locator("#sampleRunButton").wait_for(state="visible")

                page.locator("#addProblemButton").click()
                page.locator("#officialRepoInput").fill("owner/problems")
                page.locator("#packAssetInput").fill("official-e2e.aljpack")
                page.locator("#packRefInput").fill("v1.2.3")
                page.locator("#downloadPackButton").click()

                wait_for_text(page, "#packStatus", "official-e2e.aljpack")
                wait_for_text(page, "#packStatus", "체크섬 확인됨")
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
        """공식 패키지 다운로드 오류 안내 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        jobs: dict[str, dict] = {}

        def fail_download(route):
            """실패 다운로드 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
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
                page.locator("#sampleRunButton").wait_for(state="visible")

                page.locator("#addProblemButton").click()
                page.locator("#officialRepoInput").fill("owner/problems")
                page.locator("#packAssetInput").fill("missing.aljpack")
                page.locator("#downloadPackButton").click()

                wait_for_text(page, "#packStatus", "repository, ref 또는 release asset")
                wait_for_text(page, "#packStatus", "저장소, branch/tag, asset 이름을 확인")
                unexpected_errors = [
                    error
                    for error in self.browser_errors
                    if "api/packs/download" not in error and "404 (Not Found)" not in error
                ]
                self.assertEqual(unexpected_errors, [])

    def test_real_compile_error_source_is_visible_in_browser(self) -> None:
        """실제 컴파일 오류 소스 표시 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-web-real-compile-error-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#sourceTextInput").wait_for(state="visible")
                page.locator("#filenameInput").fill("main.cpp")
                page.locator("#sourceTextInput").fill("int main( { return 0; }\n")

                page.locator("#sampleRunButton").click()
                wait_for_text(page, "#statusBadge", "오류", timeout=120_000)
                wait_for_text(page, "#resultSummary", "compile failed", timeout=120_000)
                self.assert_no_browser_errors()

    def test_drag_drop_upload_and_debug_mode_render_logs(self) -> None:
        """드래그 드롭 업로드 및 디버그 모드 렌더링 로그 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        debug_env = {"ALJ_WEB_DEBUG": "1"}
        source = (ROOT / "tests" / "fixtures" / "accepted.py").read_text(encoding="utf-8")
        with isolated_runtime("alj-judge-web-debug-drop-e2e-") as (_directory, runtime):
            env = judge_env(runtime)
            env.update(debug_env)
            with temporary_env(env), run_app(create_app()) as server:
                page = self.new_page(server.url)
                stub_samples(page)
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
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
                wait_for_text(page, "#sourceReadiness", "drop_accepted.py 준비됨")

                page.locator("#sampleRunButton").click()
                wait_for_text(page, "#statusBadge", "맞았습니다", timeout=120_000)
                wait_for_text(page, "#resultOutput", "Starting judge run.", timeout=120_000)
                self.assert_no_browser_errors()

    def test_static_modules_and_styles_load_without_browser_errors(self) -> None:
        """정적 모듈 및 스타일 로드 없이 브라우저 오류 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
                page.locator("#sampleRunButton").wait_for(state="visible")
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
        """문제 및 패키지 메타데이터 이스케이프 HTML 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """잘못된 패키지 업로드 표시 모달 오류 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-web-invalid-pack-e2e-") as (_directory, runtime):
            invalid_pack = runtime / "not-a-pack.txt"
            invalid_pack.write_text("not a pack", encoding="utf-8")
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#addProblemButton").click()
                page.locator("#packFileInput").set_input_files(str(invalid_pack))
                page.locator("#uploadPackButton").click()
                wait_for_text(page, "#packStatus", ".aljpack", timeout=30_000)
                wait_for_text(page, "#toastHost", ".aljpack", timeout=30_000)
                self.assertFalse(
                    [error for error in self.browser_errors if error.startswith("pageerror:")]
                )

    def test_truncated_wrong_artifacts_are_displayed_in_browser(self) -> None:
        """잘린 오답 산출물 표시 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
                                "채점 · 06",
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
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#sourceTextInput").wait_for(state="visible")
                page.locator("#filenameInput").fill("wrong.py")
                page.locator("#sourceTextInput").fill(source)
                page.locator("#sampleRunButton").click()
                wait_for_text(page, "#statusBadge", "오답")
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
        """모바일 텍스트 실행 절차 유지 결과 표시 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        source = (ROOT / "tests" / "fixtures" / "accepted.py").read_text(encoding="utf-8")
        with isolated_runtime("alj-judge-web-mobile-run-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                page = self.new_page(server.url, width=390, height=844)
                stub_samples(page)
                page.goto(server.url)
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#problemSelect").select_option("06")
                page.locator("#sampleRunButton").wait_for(state="visible")
                page.locator("#sourceTextInput").wait_for(state="visible")
                page.locator("#filenameInput").fill("main.py")
                page.locator("#sourceTextInput").fill(source)
                assert_visible_in_viewport(self, page.locator("#sampleRunButton"))
                page.locator("#sampleRunButton").click()
                wait_for_text(page, "#statusBadge", "맞았습니다", timeout=120_000)
                page.locator("#resultSummary").scroll_into_view_if_needed()
                assert_visible_in_viewport(self, page.locator("#resultSummary"))
                self.assert_no_browser_errors()

    def test_judge_web_viewports_keep_core_controls_usable(self) -> None:
        """채점기 웹 뷰포트 유지 핵심 컨트롤 사용 가능 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-web-view-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_app()) as server:
                for width, height in [(1440, 900), (900, 900), (390, 844)]:
                    page = self.new_page(server.url, width=width, height=height)
                    page.goto(server.url)
                    page.locator("#sampleRunButton").wait_for(state="visible")
                    page.wait_for_function(
                        """() => {
                            const button = document.querySelector("#cacheManageButton");
                            return button && !button.disabled;
                        }"""
                    )
                    assert_visible_in_viewport(self, page.locator("#sampleRunButton"))
                    assert_visible_in_viewport(self, page.locator("#problemSelect"))
                    assert_visible_in_viewport(self, page.locator("#fullRunButton"))
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
