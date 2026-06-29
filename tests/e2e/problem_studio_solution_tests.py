"""Problem Studio 솔루션 브라우저 E2E 테스트입니다."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from problem_studio.core.templates import create_problem
from problem_studio.web.app import create_app
from tests.e2e.helpers import (
    BrowserE2ETestCase,
    click_by_text,
    isolated_runtime,
    run_app,
    set_solution_modal_editor_value,
    wait_for_text,
)
from tests.e2e.problem_studio_fakes import git


def completed_solution_job(
    job_id: str,
    result: dict,
    *,
    problem_id: str = "alpha",
    last_log: str = "solution verification finished",
) -> dict:
    """화면이 완료된 작업을 렌더링할 수 있도록 솔루션 작업 작업 응답 페이로드를 구성합니다.

    Args:
        job_id (str): 조회하거나 구성할 백그라운드 작업 식별자입니다.
        result (dict): 완료된 작업 응답에 포함할 결과 페이로드입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
        last_log (str): 완료된 작업 응답에 마지막 로그로 노출할 메시지입니다.

    Returns:
        dict: 완료된 솔루션 검증 작업을 나타내는 작업 큐 응답 객체입니다.
    """
    return {
        "jobId": job_id,
        "kind": "solution-verify",
        "title": "솔루션 기대 결과 검증",
        "problemId": problem_id,
        "status": "succeeded",
        "cancelSupported": True,
        "target": {"problemId": problem_id, "profile": result.get("profile")},
        "progress": {"message": last_log},
        "lastLog": last_log,
        "logs": [{"message": last_log}],
        "result": result,
    }


def completed_stress_job(job_id: str, result: dict, *, problem_id: str = "alpha") -> dict:
    """화면이 완료된 작업을 렌더링할 수 있도록 스트레스 작업 작업 응답 페이로드를 구성합니다.

    Args:
        job_id (str): 조회하거나 구성할 백그라운드 작업 식별자입니다.
        result (dict): 완료된 작업 응답에 포함할 결과 페이로드입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.

    Returns:
        dict: 완료된 스트레스 실행 작업을 나타내는 작업 큐 응답 객체입니다.
    """
    return {
        "jobId": job_id,
        "kind": "solution-stress",
        "title": "Stress 테스트",
        "problemId": problem_id,
        "status": "succeeded",
        "cancelSupported": True,
        "target": {"problemId": problem_id, "profile": result.get("profile")},
        "progress": {
            "message": "stress finished",
            "current": result.get("iterations", 0),
            "total": result.get("iterations", 1),
            "iteration": result.get("iterations", 0),
            "mismatches": result.get("mismatchCount", 0),
            "seed": result.get("mismatches", [{}])[0].get("seed"),
            "elapsedSeconds": result.get("elapsedSeconds", 0),
            "remainingSeconds": 0,
        },
        "lastLog": "stress finished",
        "logs": [{"message": "stress finished"}],
        "result": result,
    }


def route_solution_jobs(page, jobs: dict[str, dict]) -> None:
    """브라우저 테스트에서 솔루션 작업 요청을 가로채 고정된 API 응답을 제공하도록 설정합니다.

    Args:
        page (Any): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        jobs (dict[str, dict]): 브라우저 라우팅에 사용할 작업 목록 응답 데이터입니다.
    """
    page.route("**/api/jobs", lambda route: route.fulfill(json={"jobs": list(jobs.values())}))


def accepted_solution_result(
    *,
    problem_id: str,
    path: str,
    run_id: str,
    scope: str = "single",
) -> dict:
    """통과한 솔루션 검증 결과를 일관된 형태로 구성합니다.

    Args:
        problem_id (str): 결과가 속한 문제 식별자입니다.
        path (str): 검증한 솔루션 상대 경로입니다.
        run_id (str): 화면과 저장소에서 확인할 실행 식별자입니다.
        scope (str): 전체 검증 또는 개별 테스트 범위입니다.

    Returns:
        dict: 솔루션 검증 API와 작업 센터가 반환하는 결과 페이로드입니다.
    """
    return {
        "problemId": problem_id,
        "profile": "hidden",
        "scope": scope,
        "solution": path if scope == "single" else None,
        "passed": True,
        "verifiedCount": 1,
        "totalCount": 1,
        "skippedCount": 0,
        "checks": [
            {
                "path": path,
                "sourcePath": path,
                "expectedStatus": "accepted",
                "actualStatus": "accepted",
                "passed": True,
                "runId": run_id,
                "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
                "cases": [
                    {
                        "case": "hidden-1",
                        "status": "accepted",
                        "timeMs": 1,
                        "memoryBytes": 1024,
                    }
                ],
            }
        ],
    }


class ProblemStudioSolutionE2ETest(BrowserE2ETestCase):
    """Problem Studio 솔루션 브라우저 흐름을 검증합니다."""

    def test_solution_stress_mismatch_preview_and_append_in_browser(self) -> None:
        """스트레스 불일치 미리보기와 케이스 추가 흐름을 검증합니다."""
        jobs: dict[str, dict] = {}
        append_requests: list[dict] = []

        stress_result = {
            "problemId": "alpha",
            "profile": "hidden",
            "stressRunId": "stress-e2e",
            "passed": False,
            "iterations": 1,
            "durationSeconds": 60,
            "elapsedSeconds": 1.2,
            "mismatchCount": 1,
            "checkedSolutions": [
                {
                    "solution": "solutions/sneaky.wa.py",
                    "solutionKey": "solutions__sneaky_wa_py-abc123",
                    "expectedStatus": "wrong_answer",
                }
            ],
            "mismatches": [
                {
                    "caseId": "000001",
                    "caseName": "stress-000001",
                    "solution": "solutions/sneaky.wa.py",
                    "solutionKey": "solutions__sneaky_wa_py-abc123",
                    "expectedStatus": "wrong_answer",
                    "actualStatus": "accepted",
                    "seed": 981273,
                    "args": {"n": 7},
                    "generatorCaseName": "hidden-seed",
                    "inputHash": "hash",
                    "message": "expected WA but accepted",
                }
            ],
        }

        def stress_job(route):
            """스트레스 작업 응답을 구성합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            job = completed_stress_job("stress-job", stress_result)
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        def preview_route(route):
            """스트레스 mismatch 미리보기 응답을 구성합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            route.fulfill(
                json={
                    "problemId": "alpha",
                    "stressRunId": "stress-e2e",
                    "caseId": "000001",
                    "solutionKey": "solutions__sneaky_wa_py-abc123",
                    "previewLimit": 12000,
                    "metadata": stress_result["mismatches"][0],
                    "input": "42\n",
                    "expected": "42\n",
                    "actual": "42\n",
                    "diff": "",
                    "truncation": {
                        "input": {"truncated": False, "omittedChars": 0},
                        "expected": {"truncated": False, "omittedChars": 0},
                        "actual": {"truncated": False, "omittedChars": 0},
                        "diff": {"truncated": False, "omittedChars": 0},
                    },
                }
            )

        def append_route(route):
            """스트레스 케이스 추가 응답을 구성합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            append_requests.append(route.request.post_data_json or {})
            route.fulfill(
                json={
                    "problemId": "alpha",
                    "profile": "hidden",
                    "caseName": append_requests[-1].get("name") or "stress-generator",
                    "mode": append_requests[-1].get("mode") or "fixed",
                    "path": "problems/alpha/generator/cases.yml",
                    "compile": {"valid": True, "profiles": [], "diagnostics": []},
                    "files": [
                        {"path": "generator/cases.yml", "size": 1},
                        {"path": "solutions/main_solution.ac.cpp", "size": 1},
                        {"path": "solutions/sneaky.wa.py", "size": 1},
                    ],
                    "solutions": [],
                }
            )

        with isolated_runtime("alj-problem-studio-stress-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha Stress", "E2E")
            (workspace / "problems" / "alpha" / "solutions" / "sneaky.wa.py").write_text(
                "print(42)\n",
                encoding="utf-8",
            )
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                route_solution_jobs(page, jobs)
                page.route("**/api/problems/*/solutions/stress/jobs", stress_job)
                page.route(
                    "**/api/problems/alpha/solutions/stress/runs/stress-e2e/"
                    "mismatches/000001/solutions__sneaky_wa_py-abc123",
                    preview_route,
                )
                page.route(
                    "**/api/problems/alpha/solutions/stress/runs/stress-e2e/"
                    "mismatches/000001/solutions__sneaky_wa_py-abc123/append",
                    append_route,
                )
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="solutions"]').click()
                click_by_text(page, "#tabActions button", "Stress 테스트")
                page.locator("#solutionStressModal").wait_for(state="visible")
                wait_for_text(page, "#solutionStressSelection", "sneaky.wa.py")
                page.locator("#solutionStressStartButton").click()
                wait_for_text(page, "#solutionValidationSummary", "Stress mismatch")
                page.locator("[data-stress-preview='000001']").first.click()
                page.locator("#solutionStressReviewModal").wait_for(state="visible")
                wait_for_text(page, "#solutionStressReviewBody", "981273")
                page.locator("#stressAppendMode").select_option("generator")
                page.locator("#stressAppendButton").click()
                wait_for_text(page, "#alertStack", "데이터 추가 완료")
                self.assertEqual(append_requests[-1]["mode"], "generator")
                self.assert_no_browser_errors()

    def test_solution_mismatch_artifact_preview_in_browser(self) -> None:
        """솔루션 불일치 산출물 미리보기 흐름을 검증합니다."""
        jobs: dict[str, dict] = {}

        def verify_job(route):
            """검증 작업 응답을 구성합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            result = {
                "problemId": "alpha",
                "profile": "hidden",
                "passed": False,
                "verifiedCount": 1,
                "totalCount": 1,
                "skippedCount": 0,
                "checks": [
                    {
                        "path": "solutions/main_solution.ac.cpp",
                        "sourcePath": "solutions/main_solution.ac.cpp",
                        "expectedStatus": "accepted",
                        "actualStatus": "wrong_answer",
                        "passed": False,
                        "message": "forced mismatch",
                        "runId": "e2e-run",
                        "metrics": {"maxTimeMs": 2, "maxMemoryBytes": 2048},
                        "cases": [
                            {
                                "case": "hidden-1",
                                "status": "wrong_answer",
                                "timeMs": 2,
                                "memoryBytes": 2048,
                            }
                        ],
                    }
                ],
            }
            job = completed_solution_job("solution-mismatch", result)
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        def artifact_route(route):
            """산출물 미리보기 응답을 구성합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            route.fulfill(
                json={
                    "problemId": "alpha",
                    "previewLimit": 12000,
                    "input": "1\n",
                    "expected": "1\n",
                    "actual": "0\n",
                    "diff": "--- expected\n+++ actual\n@@\n-1\n+0\n",
                    "truncation": {
                        "input": {"truncated": False, "omittedChars": 0},
                        "expected": {"truncated": False, "omittedChars": 0},
                        "actual": {"truncated": False, "omittedChars": 0},
                        "diff": {"truncated": False, "omittedChars": 0},
                    },
                }
            )

        with isolated_runtime("alj-problem-studio-solution-artifact-e2e-") as (
            _directory,
            workspace,
        ):
            create_problem(workspace, "alpha", "Alpha Mismatch", "E2E")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                route_solution_jobs(page, jobs)
                page.route("**/api/problems/*/solutions/verify/jobs", verify_job)
                page.route(
                    "**/api/problems/alpha/solutions/runs/e2e-run/wrong/hidden-1",
                    artifact_route,
                )
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="solutions"]').click()
                click_by_text(page, "#tabActions button", "기대 결과 검증")
                wait_for_text(page, "#alertStack", "기대 결과와 다른 솔루션")
                page.locator("[data-solution-cases]").first.click()
                page.locator("#solutionCasesModal").wait_for(state="visible")
                page.locator("[data-solution-artifact-case='hidden-1']").click()
                wait_for_text(page, "#solutionArtifactPreview", "e2e-run")
                wait_for_text(page, "#solutionArtifactPreview", "1")
                page.locator("[data-solution-artifact-tab='diff']").click()
                wait_for_text(page, "#solutionArtifactPreview", "--- expected")
                self.assertGreater(
                    page.locator("#solutionArtifactPreview .diff-remove").count(),
                    0,
                )
                self.assert_no_browser_errors()

    def test_full_solution_verify_shows_verifying_state_over_previous_result(self) -> None:
        """전체 검증 시작 직후 이전 결과 대신 검증중 상태를 검증합니다."""
        verify_requests: list[dict] = []
        jobs: dict[str, dict] = {}

        completed_result = {
            "problemId": "alpha",
            "profile": "hidden",
            "scope": "all",
            "passed": True,
            "verifiedCount": 1,
            "totalCount": 1,
            "skippedCount": 0,
            "checks": [
                {
                    "path": "solutions/main_solution.ac.cpp",
                    "sourcePath": "solutions/main_solution.ac.cpp",
                    "expectedStatus": "accepted",
                    "actualStatus": "accepted",
                    "passed": True,
                    "runId": "previous-run",
                    "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
                    "cases": [
                        {
                            "case": "hidden-1",
                            "status": "accepted",
                            "timeMs": 1,
                            "memoryBytes": 1024,
                        }
                    ],
                }
            ],
        }
        finished_after_switch = {
            **completed_result,
            "checks": [
                {
                    **completed_result["checks"][0],
                    "runId": "alpha-finished-after-switch",
                }
            ],
        }

        def verify_job(route):
            """완료와 running 검증 작업 응답을 차례로 구성합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            body = route.request.post_data_json or {}
            verify_requests.append(body)
            if len(verify_requests) == 1:
                job = completed_solution_job("solution-previous", completed_result)
            else:
                job = {
                    "jobId": "solution-running",
                    "kind": "solution-verify",
                    "title": "솔루션 기대 결과 검증",
                    "problemId": "alpha",
                    "status": "running",
                    "cancelSupported": True,
                    "target": {
                        "problemId": "alpha",
                        "profile": "hidden",
                        "scope": "all",
                    },
                    "progress": {"message": "verifying solutions"},
                    "lastLog": "verifying solutions",
                    "logs": [{"message": "verifying solutions"}],
                    "result": None,
                }
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        with isolated_runtime("alj-problem-studio-solution-verifying-e2e-") as (
            _directory,
            workspace,
        ):
            create_problem(workspace, "alpha", "Alpha Verifying", "E2E")
            create_problem(workspace, "beta", "Beta Verifying", "E2E")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                route_solution_jobs(page, jobs)
                page.route("**/api/problems/*/solutions/verify/jobs", verify_job)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="solutions"]').click()
                click_by_text(page, "#tabActions button", "기대 결과 검증")
                wait_for_text(page, "#alertStack", "Solutions verified.")
                wait_for_text(page, "#tabFiles", "기대 AC · 일치")
                self.assertIsNone(verify_requests[-1].get("solutions"))

                click_by_text(page, "#tabActions button", "기대 결과 검증")
                wait_for_text(page, "#tabFiles", "검증중")
                self.assertNotIn("previous-run", page.locator("#tabFiles").inner_text())
                self.assertIsNone(verify_requests[-1].get("solutions"))

                page.locator("#problemList .list-item").filter(has_text="beta").click()
                wait_for_text(page, "#problemTitle", "Beta Verifying")
                jobs["solution-running"] = completed_solution_job(
                    "solution-running",
                    finished_after_switch,
                    problem_id="alpha",
                    last_log="alpha verify finished after switch",
                )
                page.wait_for_function(
                    """() => {
                        const raw = localStorage.getItem("problem-studio:last-results:v1");
                        return raw && raw.includes("alpha-finished-after-switch");
                    }"""
                )
                self.assertNotIn(
                    "alpha-finished-after-switch",
                    page.locator("#tabFiles").inner_text(),
                )
                self.assert_no_browser_errors()

    def test_full_solution_verify_applies_partial_progress_before_completion(self) -> None:
        """전체 검증 job이 끝나기 전 완료된 솔루션 row가 partial progress로 갱신되는지 검증합니다."""
        jobs: dict[str, dict] = {}
        verify_requests: list[dict] = []

        def verify_job(route):
            body = route.request.post_data_json or {}
            verify_requests.append(body)
            job = {
                "jobId": "solution-partial-running",
                "kind": "solution-verify",
                "title": "솔루션 기대 결과 검증",
                "problemId": "alpha",
                "status": "running",
                "cancelSupported": True,
                "target": {
                    "problemId": "alpha",
                    "profile": "hidden",
                    "scope": "all",
                },
                "progress": {
                    "message": "solutions/main_solution.ac.cpp verified: accepted",
                    "current": 1,
                    "total": 2,
                    "partialSummary": {
                        "verifiedCount": 1,
                        "failedCount": 0,
                        "totalCount": 2,
                    },
                    "partialCheck": {
                        "source": "problems/alpha/solutions/main_solution.ac.cpp",
                        "expectedStatus": "accepted",
                        "actualStatus": "accepted",
                        "rawActualStatus": "accepted",
                        "passed": True,
                        "runId": "partial-visible-run",
                        "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
                        "cases": [
                            {
                                "case": "hidden-1",
                                "status": "ok",
                                "timeMs": 1,
                                "memoryBytes": 1024,
                            }
                        ],
                    },
                },
                "lastLog": "solutions/main_solution.ac.cpp verified: accepted",
                "logs": [{"message": "solutions/main_solution.ac.cpp verified: accepted"}],
                "result": None,
            }
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        with isolated_runtime("alj-problem-studio-solution-partial-e2e-") as (
            _directory,
            workspace,
        ):
            create_problem(workspace, "alpha", "Alpha Partial", "E2E")
            extra = workspace / "problems" / "alpha" / "solutions" / "extra_solution.wa.py"
            extra.write_text("print(0)\n", encoding="utf-8")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                route_solution_jobs(page, jobs)
                page.route("**/api/problems/*/solutions/verify/jobs", verify_job)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="solutions"]').click()

                click_by_text(page, "#tabActions button", "기대 결과 검증")
                wait_for_text(page, "#tabFiles", "검증 중 · 기대 AC 일치")
                wait_for_text(page, "#tabFiles", "partial-visible-run")
                wait_for_text(page, "#tabFiles", "extra_solution.wa.py")
                wait_for_text(page, "#tabFiles", "검증중")
                self.assertIsNone(verify_requests[-1].get("solutions"))
                self.assert_no_browser_errors()

    def test_single_solution_test_completion_after_problem_switch_is_scoped(self) -> None:
        """문제 전환 중 완료된 개별 테스트의 저장 범위를 검증합니다."""
        jobs: dict[str, dict] = {}
        single_result = {
            "problemId": "alpha",
            "profile": "hidden",
            "scope": "single",
            "solution": "solutions/main_solution.ac.cpp",
            "passed": True,
            "verifiedCount": 1,
            "totalCount": 1,
            "skippedCount": 0,
            "checks": [
                {
                    "path": "solutions/main_solution.ac.cpp",
                    "sourcePath": "solutions/main_solution.ac.cpp",
                    "expectedStatus": "accepted",
                    "actualStatus": "accepted",
                    "passed": True,
                    "runId": "single-after-switch",
                    "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
                    "cases": [
                        {
                            "case": "hidden-1",
                            "status": "accepted",
                            "timeMs": 1,
                            "memoryBytes": 1024,
                        }
                    ],
                }
            ],
        }

        def single_test_job(route):
            """개별 테스트 작업을 running 상태로 시작해 문제 전환 중 완료되는 상황을 만듭니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            job = {
                "jobId": "single-running",
                "kind": "solution-test",
                "title": "개별 테스트",
                "problemId": "alpha",
                "status": "running",
                "cancelSupported": True,
                "target": {
                    "problemId": "alpha",
                    "profile": "hidden",
                    "solution": "solutions/main_solution.ac.cpp",
                    "scope": "single",
                },
                "progress": {"message": "single test running"},
                "lastLog": "single test running",
                "logs": [{"message": "single test running"}],
                "result": None,
            }
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        with isolated_runtime("alj-problem-studio-solution-switch-e2e-") as (
            _directory,
            workspace,
        ):
            create_problem(workspace, "alpha", "Alpha Single Switch", "E2E")
            create_problem(workspace, "beta", "Beta Single Switch", "E2E")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                route_solution_jobs(page, jobs)
                page.route("**/api/problems/*/solutions/test/jobs", single_test_job)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="solutions"]').click()
                page.locator('[data-solution-test="solutions/main_solution.ac.cpp"]').click()
                wait_for_text(page, "#tabFiles", "개별 테스트 중")

                page.locator("#problemList .list-item").filter(has_text="beta").click()
                wait_for_text(page, "#problemTitle", "Beta Single Switch")
                jobs["single-running"] = completed_solution_job(
                    "single-running",
                    single_result,
                    problem_id="alpha",
                    last_log="single test finished after switch",
                )
                jobs["single-running"]["kind"] = "solution-test"
                page.wait_for_function(
                    """() => {
                        const raw = localStorage.getItem("problem-studio:last-results:v1");
                        return raw && raw.includes("single-after-switch");
                    }"""
                )
                self.assertNotIn("single-after-switch", page.locator("#tabFiles").inner_text())
                self.assert_no_browser_errors()

    def test_single_solution_test_terminal_jobs_clear_active_state(self) -> None:
        """개별 테스트 terminal job이 row 진행 상태를 정리하는지 검증합니다."""
        jobs: dict[str, dict] = {}
        request_count = 0

        def single_test_job(route):
            """개별 테스트 작업을 running으로 시작하고 테스트 본문에서 terminal 상태로 전환합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            nonlocal request_count
            request_count += 1
            job_id = f"single-terminal-{request_count}"
            job = {
                "jobId": job_id,
                "kind": "solution-test",
                "title": "개별 테스트",
                "problemId": "alpha",
                "status": "running",
                "cancelSupported": True,
                "target": {
                    "problemId": "alpha",
                    "profile": "hidden",
                    "solution": "solutions/main_solution.ac.cpp",
                    "scope": "single",
                },
                "progress": {"message": "single test running"},
                "lastLog": "single test running",
                "logs": [{"message": "single test running"}],
                "result": None,
            }
            jobs[job_id] = job
            route.fulfill(json=job)

        with isolated_runtime("alj-problem-studio-solution-terminal-e2e-") as (
            _directory,
            workspace,
        ):
            create_problem(workspace, "alpha", "Alpha Terminal", "E2E")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                route_solution_jobs(page, jobs)
                page.route("**/api/problems/*/solutions/test/jobs", single_test_job)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="solutions"]').click()

                for status, message in [
                    ("failed", "forced single failure"),
                    ("cancelled", "취소됨"),
                    ("stale", "만료됨"),
                ]:
                    page.locator('[data-solution-test="solutions/main_solution.ac.cpp"]').click()
                    wait_for_text(page, "#tabFiles", "개별 테스트 중")
                    job = jobs[f"single-terminal-{request_count}"]
                    job["status"] = status
                    job["error"] = "forced single failure" if status == "failed" else None
                    job["lastLog"] = message
                    job["progress"] = {"message": message}
                    wait_for_text(page, "#alertStack", message)
                    page.wait_for_function(
                        """() => !document.querySelector("#tabFiles")?.textContent
                            .includes("개별 테스트 중")"""
                    )
                    self.assertNotIn("개별 테스트 중", page.locator("#tabFiles").inner_text())

                self.assert_no_browser_errors()

    def test_single_solution_test_completion_after_repository_switch_is_scoped(self) -> None:
        """저장소 전환 중 완료된 개별 테스트의 저장 범위를 검증합니다."""
        jobs: dict[str, dict] = {}
        current_repository_scope = {"value": "repo:repo-a"}
        scoped_job_reads: list[str] = []
        solution_path = "solutions/main_solution.ac.cpp"
        result = accepted_solution_result(
            problem_id="01",
            path=solution_path,
            run_id="repo-a-single-run",
        )

        def visible_jobs(route):
            """현재 화면 저장소에 보이는 작업만 목록 응답에 포함합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            route.fulfill(
                json={
                    "jobs": [
                        job
                        for job in jobs.values()
                        if job.get("target", {}).get("repositoryScope")
                        == current_repository_scope["value"]
                    ]
                }
            )

        def scoped_job(route):
            """waiter가 캡처한 repository_scope로 완료 작업을 조회하는 경로를 검증합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            parsed = urlparse(route.request.url)
            job_id = parsed.path.rsplit("/", 1)[-1]
            scope = parse_qs(parsed.query).get("repository_scope", [""])[0]
            scoped_job_reads.append(scope)
            job = jobs.get(job_id)
            if job and job.get("target", {}).get("repositoryScope") == scope:
                route.fulfill(json=job)
            else:
                route.fulfill(status=404, json={"detail": "job not found"})

        def single_test_job(route):
            """repo-a에서 시작한 개별 테스트 작업을 running 상태로 반환합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            job = {
                "jobId": "repo-a-single",
                "kind": "solution-test",
                "title": "개별 테스트",
                "problemId": "01",
                "status": "running",
                "cancelSupported": True,
                "target": {
                    "problemId": "01",
                    "profile": "hidden",
                    "solution": solution_path,
                    "scope": "single",
                    "repositoryName": "repo-a",
                    "repositoryScope": "repo:repo-a",
                },
                "progress": {"message": "repo-a single test running"},
                "lastLog": "repo-a single test running",
                "logs": [{"message": "repo-a single test running"}],
                "result": None,
            }
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        with isolated_runtime("alj-problem-studio-solution-repo-switch-e2e-") as (
            _directory,
            root,
        ):
            workspace = root / "studio"
            repo_a = workspace / "problems" / "repo-a"
            repo_b = workspace / "problems" / "repo-b"
            create_problem(repo_a, "01", "Repo A Solution", "E2E")
            create_problem(repo_b, "01", "Repo B Solution", "E2E")
            git(repo_a, "init")
            git(repo_b, "init")

            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.route("**/api/jobs", visible_jobs)
                page.route("**/api/jobs/*", scoped_job)
                page.route("**/api/problems/*/solutions/test/jobs", single_test_job)
                page.goto(server.url)
                page.locator("#repositorySelect").wait_for(state="visible")
                page.locator("#repositoryRefreshButton").click()
                page.locator("#repositoryCloneButton").click()
                page.locator("#repositoryNameInput").fill("repo-a")
                page.locator("#repositoryRegisterButton").click()
                wait_for_text(page, "#problemTitle", "Repo A Solution")
                page.locator('[data-tab="solutions"]').click()
                page.locator(f'[data-solution-test="{solution_path}"]').click()
                wait_for_text(page, "#tabFiles", "개별 테스트 중")

                current_repository_scope["value"] = "repo:repo-b"
                page.locator("#repositorySelect").select_option("repo-b")
                wait_for_text(page, "#problemTitle", "Repo B Solution")
                jobs["repo-a-single"].update(
                    {
                        "status": "succeeded",
                        "result": result,
                        "progress": {"message": "repo-a single finished"},
                        "lastLog": "repo-a single finished",
                    }
                )
                page.wait_for_function(
                    """() => {
                        const raw = localStorage.getItem("problem-studio:last-results:v1");
                        if (!raw) return false;
                        const data = JSON.parse(raw);
                        const repoA = data["repo-a:01"];
                        const repoB = data["repo-b:01"];
                        const stored = repoA?.solutionTestResultsByPath
                            ?.["solutions/main_solution.ac.cpp"]?.checks?.[0]?.runId;
                        return stored === "repo-a-single-run"
                            && !JSON.stringify(repoB || {}).includes("repo-a-single-run");
                    }"""
                )
                self.assertIn("repo:repo-a", scoped_job_reads)
                self.assertNotIn("repo-a-single-run", page.locator("#tabFiles").inner_text())

                current_repository_scope["value"] = "repo:repo-a"
                page.locator("#repositorySelect").select_option("repo-a")
                wait_for_text(page, "#problemTitle", "Repo A Solution")
                page.locator('[data-tab="solutions"]').click()
                wait_for_text(page, "#tabFiles", "repo-a-single-run")
                self.assert_no_browser_errors()

    def test_full_solution_verify_failure_clears_previous_result(self) -> None:
        """전체 검증 실패 시에도 검증 시작 전에 있던 기대 결과가 다시 노출되지 않는지 검증합니다."""
        verify_requests: list[dict] = []
        jobs: dict[str, dict] = {}
        previous_result = {
            "problemId": "alpha",
            "profile": "hidden",
            "scope": "all",
            "passed": True,
            "verifiedCount": 1,
            "totalCount": 1,
            "skippedCount": 0,
            "checks": [
                {
                    "path": "solutions/main_solution.ac.cpp",
                    "sourcePath": "solutions/main_solution.ac.cpp",
                    "expectedStatus": "accepted",
                    "actualStatus": "accepted",
                    "passed": True,
                    "runId": "previous-preserved",
                    "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
                    "cases": [
                        {
                            "case": "hidden-1",
                            "status": "accepted",
                            "timeMs": 1,
                            "memoryBytes": 1024,
                        }
                    ],
                }
            ],
        }

        def verify_job(route):
            """첫 요청은 성공, 두 번째 요청은 실패 job으로 반환합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            verify_requests.append(route.request.post_data_json or {})
            if len(verify_requests) == 1:
                job = completed_solution_job("solution-preserved", previous_result)
            else:
                job = {
                    "jobId": "solution-failed",
                    "kind": "solution-verify",
                    "title": "솔루션 기대 결과 검증",
                    "problemId": "alpha",
                    "status": "failed",
                    "cancelSupported": True,
                    "target": {"problemId": "alpha", "profile": "hidden", "scope": "all"},
                    "progress": {"message": "verification failed"},
                    "lastLog": "verification failed",
                    "logs": [{"message": "verification failed"}],
                    "error": "forced verification failure",
                    "result": None,
                }
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        with isolated_runtime("alj-problem-studio-solution-fail-e2e-") as (
            _directory,
            workspace,
        ):
            create_problem(workspace, "alpha", "Alpha Failure Preserve", "E2E")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                route_solution_jobs(page, jobs)
                page.route("**/api/problems/*/solutions/verify/jobs", verify_job)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="solutions"]').click()
                click_by_text(page, "#tabActions button", "기대 결과 검증")
                wait_for_text(page, "#alertStack", "Solutions verified.")
                wait_for_text(page, "#tabFiles", "previous-preserved")

                click_by_text(page, "#tabActions button", "기대 결과 검증")
                wait_for_text(page, "#tabFiles", "검증중")
                self.assertNotIn("previous-preserved", page.locator("#tabFiles").inner_text())
                wait_for_text(page, "#alertStack", "forced verification failure")
                self.assertNotIn("previous-preserved", page.locator("#tabFiles").inner_text())
                self.assert_no_browser_errors()

    def test_solution_upload_rename_edit_full_verify_and_single_test(self) -> None:
        """솔루션 업로드, 편집, 전체 검증, 개별 테스트 흐름을 검증합니다."""
        verify_requests: list[dict] = []
        single_test_requests: list[dict] = []
        jobs: dict[str, dict] = {}

        def verify_job(route):
            """전체 검증 작업 응답을 구성합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            body = route.request.post_data_json or {}
            verify_requests.append(body)
            problem_root = workspace / "problems" / "alpha"
            all_paths = [
                path.relative_to(problem_root).as_posix()
                for path in sorted((problem_root / "solutions").glob("*"))
                if path.is_file()
            ]
            requested = body.get("solutions") or all_paths
            result = {
                "problemId": "alpha",
                "profile": "hidden",
                "passed": True,
                "verifiedCount": len(requested),
                "totalCount": len(requested),
                "skippedCount": 0,
                "checks": [
                    {
                        "path": path,
                        "sourcePath": path,
                        "expectedStatus": "accepted",
                        "actualStatus": "accepted",
                        "passed": True,
                        "runId": f"verify-{index}",
                        "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
                        "cases": [
                            {
                                "case": "hidden-1",
                                "status": "accepted",
                                "timeMs": 1,
                                "memoryBytes": 1024,
                            }
                        ],
                    }
                    for index, path in enumerate(requested, start=1)
                ],
            }
            job_id = f"solution-success-{len(verify_requests)}"
            job = completed_solution_job(job_id, result)
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        def single_test_job(route):
            """개별 테스트 작업 응답을 구성합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            body = route.request.post_data_json or {}
            single_test_requests.append(body)
            path = body.get("solution") or "solutions/main_solution.ac.cpp"
            result = {
                "problemId": "alpha",
                "profile": "hidden",
                "scope": "single",
                "solution": path,
                "passed": True,
                "verifiedCount": 1,
                "totalCount": 1,
                "skippedCount": 0,
                "checks": [
                    {
                        "path": path,
                        "sourcePath": path,
                        "expectedStatus": "accepted",
                        "actualStatus": "accepted",
                        "passed": True,
                        "runId": "single-test-run",
                        "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
                        "cases": [
                            {
                                "case": "hidden-1",
                                "status": "accepted",
                                "timeMs": 1,
                                "memoryBytes": 1024,
                            }
                        ],
                    }
                ],
            }
            job = completed_solution_job(
                f"solution-single-{len(single_test_requests)}",
                result,
                last_log="single solution test finished",
            )
            job["kind"] = "solution-test"
            job["title"] = "개별 테스트"
            job["target"]["solution"] = path
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        with isolated_runtime("alj-problem-studio-solution-edit-e2e-") as (
            _directory,
            workspace,
        ):
            create_problem(workspace, "alpha", "Alpha Solutions", "E2E")
            upload = workspace / "uploaded.wa.py"
            upload.write_text("print(0)\n", encoding="utf-8")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                route_solution_jobs(page, jobs)
                page.route("**/api/problems/*/solutions/verify/jobs", verify_job)
                page.route("**/api/problems/*/solutions/test/jobs", single_test_job)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="solutions"]').click()
                page.locator("#solutionUploadInput").set_input_files(str(upload))
                wait_for_text(page, "#tabFiles", "uploaded.wa.py")
                wait_for_text(page, "#resourceSummary", "재검증")

                click_by_text(page, "#tabActions button", "기대 결과 검증")
                wait_for_text(page, "#alertStack", "Solutions verified.")
                self.assertIsNone(verify_requests[-1].get("solutions"))

                page.locator('[data-solution-edit="solutions/uploaded.wa.py"]').click()
                page.locator("#solutionEditModal").wait_for(state="visible")
                page.locator("#solutionName").fill("renamed")
                page.locator("#solutionExpected").select_option("ac")
                page.locator("#solutionLanguage").select_option("python")
                set_solution_modal_editor_value(page, "edit", "print('renamed')\n")
                page.locator("#solutionEditModal .CodeMirror textarea").evaluate(
                    "(element) => element.focus()"
                )
                page.keyboard.press("Control+S")
                page.locator("#solutionEditModal").wait_for(state="hidden")
                wait_for_text(page, "#tabFiles", "renamed.ac.py")
                solution_dir = workspace / "problems" / "alpha" / "solutions"
                self.assertFalse((solution_dir / "uploaded.wa.py").exists())
                self.assertTrue((solution_dir / "renamed.ac.py").exists())

                page.locator('[data-solution-test="solutions/renamed.ac.py"]').click()
                wait_for_text(page, "#alertStack", "Single solution tested.")
                wait_for_text(page, "#tabFiles", "전체 재검증 필요")
                self.assertEqual(single_test_requests[-1]["solution"], "solutions/renamed.ac.py")

                click_by_text(page, "#tabActions button", "기대 결과 검증")
                wait_for_text(page, "#alertStack", "Solutions verified.")
                self.assertIsNone(verify_requests[-1].get("solutions"))

                click_by_text(page, "#tabActions button", "기대 결과 검증")
                wait_for_text(page, "#alertStack", "Solutions verified.")
                self.assertIsNone(verify_requests[-1].get("solutions"))

                dialogs: list[str] = []
                page.on(
                    "dialog",
                    lambda dialog: (dialogs.append(dialog.message), dialog.accept()),
                )
                page.locator('[data-solution-delete="solutions/renamed.ac.py"]').click()
                wait_for_text(page, "#alertStack", "솔루션 파일을 삭제했습니다.")
                page.locator('[data-solution-delete="solutions/renamed.ac.py"]').wait_for(
                    state="detached"
                )
                self.assertFalse((solution_dir / "renamed.ac.py").exists())
                self.assertTrue(any("solutions/renamed.ac.py" in text for text in dialogs))
                self.assert_no_browser_errors()
