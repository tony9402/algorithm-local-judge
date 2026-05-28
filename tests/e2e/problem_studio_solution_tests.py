from __future__ import annotations

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


def completed_solution_job(
    job_id: str,
    result: dict,
    *,
    problem_id: str = "alpha",
    last_log: str = "solution verification finished",
) -> dict:
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
    page.route("**/api/jobs", lambda route: route.fulfill(json={"jobs": list(jobs.values())}))


class ProblemStudioSolutionE2ETest(BrowserE2ETestCase):
    def test_solution_stress_mismatch_preview_and_append_in_browser(self) -> None:
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
            job = completed_stress_job("stress-job", stress_result)
            jobs[job["jobId"]] = job
            route.fulfill(json=job)

        def preview_route(route):
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
                    "**/api/problems/alpha/solutions/stress/runs/stress-e2e/mismatches/000001/solutions__sneaky_wa_py-abc123",
                    preview_route,
                )
                page.route(
                    "**/api/problems/alpha/solutions/stress/runs/stress-e2e/mismatches/000001/solutions__sneaky_wa_py-abc123/append",
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
        jobs: dict[str, dict] = {}

        def verify_job(route):
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

    def test_solution_upload_rename_edit_and_incremental_verify(self) -> None:
        verify_requests: list[dict] = []
        jobs: dict[str, dict] = {}

        def verify_job(route):
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

                click_by_text(page, "#tabActions button", "기대 결과 검증")
                wait_for_text(page, "#alertStack", "Solutions verified.")
                self.assertEqual(verify_requests[-1].get("solutions"), ["solutions/renamed.ac.py"])
                self.assert_no_browser_errors()
