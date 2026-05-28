"""문제 스튜디오의 검증 작업, 솔루션 실행, 패키지 빌드, 일괄 빌드 화면 흐름을 브라우저에서 검증하는 모듈입니다."""

from __future__ import annotations

import json
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from problem_studio.core.templates import create_problem
from problem_studio.core.workspace import link_testlib
from problem_studio.web.app import create_app
from tests.e2e.helpers import (
    BrowserE2ETestCase,
    click_by_text,
    isolated_runtime,
    run_app,
    run_dir_from_stdout,
    run_judge_cli,
    set_solution_modal_editor_value,
    set_studio_editor_value,
    wait_for_studio_file_ready,
    wait_for_text,
    write_trivial_python_source,
)
from tests.e2e.problem_studio_fakes import (
    fake_build_problem_pack,
    fake_build_runnable_pack,
    fake_bulk_build,
    fake_bulk_build_partial,
    fake_cancellable_slow_build_runnable_pack,
    fake_cancellable_slow_bulk_build,
    fake_compile_problem_tools,
    fake_slow_build_runnable_pack,
    fake_validate_all_data,
    fake_verify_solutions,
    git,
)


def completed_studio_job(
    job_id: str,
    kind: str,
    title: str,
    result: dict,
    *,
    problem_id: str = "alpha",
    last_log: str = "job finished",
) -> dict:
    """화면이 완료된 작업을 렌더링할 수 있도록 스튜디오 작업 작업 응답 페이로드를 구성합니다.

    Args:
        job_id (str): 조회하거나 구성할 백그라운드 작업 식별자입니다.
        kind (str): 작업 큐 화면에서 구분할 작업 종류입니다.
        title (str): 작업 목록이나 문제 메타데이터에 표시할 제목입니다.
        result (dict): 완료된 작업 응답에 포함할 결과 페이로드입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
        last_log (str): 완료된 작업 응답에 마지막 로그로 노출할 메시지입니다.

    Returns:
        dict: 완료된 문제 스튜디오 작업을 나타내는 작업 큐 응답 객체입니다.
    """
    return {
        "jobId": job_id,
        "kind": kind,
        "title": title,
        "problemId": problem_id,
        "status": "succeeded",
        "cancelSupported": True,
        "target": {"problemId": problem_id},
        "progress": {"message": last_log},
        "lastLog": last_log,
        "logs": [{"message": last_log}],
        "result": result,
    }


def route_studio_jobs(page, jobs: dict[str, dict]) -> None:
    """브라우저 테스트에서 스튜디오 작업 요청을 가로채 고정된 API 응답을 제공하도록 설정합니다.

    Args:
        page (Any): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        jobs (dict[str, dict]): 브라우저 라우팅에 사용할 작업 목록 응답 데이터입니다.
    """
    page.route("**/api/jobs", lambda route: route.fulfill(json={"jobs": list(jobs.values())}))


class ProblemStudioBuildE2ETest(BrowserE2ETestCase):
    """문제 스튜디오 빌드 종단 간 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_validation_actions_are_queued_without_blocking_workspace_in_browser(self) -> None:
        """검증 동작 대기 중 없이 차단 작업공간 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        active_jobs = {"count": 0, "max": 0, "total": 0}

        def slow_validate_all_data(*args, progress=None, **kwargs) -> dict:
            """느린 검증 전체 데이터 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                progress (Any): 가짜 실행기가 진행 로그를 전달할 콜백입니다.
                kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
            active_jobs["count"] += 1
            active_jobs["total"] += 1
            active_jobs["max"] = max(active_jobs["max"], active_jobs["count"])
            time.sleep(1.2)
            if progress:
                progress("Validating generated case hidden_1 (1/1).")
            active_jobs["count"] -= 1
            return {
                "problemId": "alpha",
                "profileCount": 1,
                "caseCount": 1,
                "profiles": [{"name": "hidden", "caseCount": 1}],
            }

        with isolated_runtime("alj-problem-studio-validation-queue-e2e-") as (
            _directory,
            workspace,
        ):
            create_problem(workspace, "alpha", "Alpha Queue", "E2E")
            with (
                patch("problem_studio.web.routes.cases.validate_all_data", slow_validate_all_data),
                run_app(create_app(workspace)) as server,
            ):
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="validator"]').click()
                click_by_text(page, "#tabActions button", "모든 데이터 생성+검증")
                click_by_text(page, "#tabActions button", "모든 데이터 생성+검증")
                wait_for_text(page, "#jobCenterButton", "작업")

                page.locator('[data-tab="info"]').click()
                wait_for_text(page, "#taskTitle", "문제 정보")
                self.assertFalse(page.locator("#metadataTitle").is_disabled())

                page.wait_for_function(
                    "() => document.querySelector('#alertStack')?.textContent"
                    ".includes('Validated 1 case')",
                    timeout=15_000,
                )
                page.locator("#jobCenterButton").click()
                page.locator('[data-job-filter="done"]').click()
                wait_for_text(page, "#jobCenterList", "완료")
                self.assertEqual(active_jobs["total"], 2)
                self.assertEqual(active_jobs["max"], 1)
                self.assert_no_browser_errors()

    def test_solution_run_all_pack_and_bulk_build_ui_in_browser(self) -> None:
        """솔루션 실행 전체 패키지 및 일괄 빌드 화면 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-problem-studio-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha Build", "E2E")
            create_problem(workspace, "beta", "Beta Build", "E2E")
            patches = [
                patch(
                    "problem_studio.web.routes.tools.compile_problem_tools",
                    fake_compile_problem_tools,
                ),
                patch("problem_studio.web.routes.cases.validate_all_data", fake_validate_all_data),
                patch(
                    "problem_studio.web.routes.solutions.verify_solutions",
                    fake_verify_solutions,
                ),
                patch(
                    "problem_studio.web.routes.checks.compile_problem_tools",
                    fake_compile_problem_tools,
                ),
                patch(
                    "problem_studio.web.routes.checks.validate_all_data",
                    fake_validate_all_data,
                ),
                patch(
                    "problem_studio.web.routes.checks.verify_solutions",
                    fake_verify_solutions,
                ),
                patch(
                    "problem_studio.web.routes.packs.build_problem_pack",
                    fake_build_problem_pack,
                ),
                patch("problem_studio.web.routes.bulk.build_all_problem_packs", fake_bulk_build),
            ]
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                with run_app(create_app(workspace)) as server:
                    page = self.new_page(server.url)
                    page.goto(server.url)
                    page.locator("#newProblemButton").wait_for(state="visible")
                    wait_for_text(page, "#problemTitle", "Alpha Build")

                    page.locator('[data-tab="solutions"]').click()
                    wait_for_text(page, "#tabFiles", "main_solution.ac.cpp")
                    click_by_text(page, "#tabActions button", "새 솔루션 파일 만들기")
                    page.locator("#solutionCreateName").fill("extra")
                    page.locator("#solutionCreateExpected").select_option("ac")
                    page.locator("#solutionCreateLanguage").select_option("python")
                    set_solution_modal_editor_value(page, "create", "print(input())\n")
                    page.locator("#solutionCreateButton").click()
                    wait_for_text(page, "#tabFiles", "extra.ac.py")

                    click_by_text(page, "#tabActions button", "기대 결과 검증")
                    wait_for_text(page, "#alertStack", "Solutions verified.")
                    wait_for_text(page, "#tabFiles", "AC")
                    page.locator("[data-solution-cases]").first.click()
                    wait_for_text(page, "#solutionCasesBody", "hidden-1")
                    page.keyboard.press("Escape")
                    page.locator("#solutionCasesModal").wait_for(state="hidden")

                    page.locator('[data-tab="build"]').click()
                    page.locator("#buildDashboard").wait_for(state="visible")
                    click_by_text(page, "#tabActions button", "전체 테스트")
                    wait_for_text(page, "#buildDashboardTitle", "전체 테스트 통과")
                    page.locator("#packButton").click()
                    wait_for_text(page, "#alertStack", "팩 빌드 완료", timeout=30_000)
                    wait_for_text(page, "#buildDashboardPack", "basic-e2e.aljpack")

                    page.locator("#workspaceBuildAllButton").click()
                    wait_for_text(page, "#workspaceBuildModal", "Alpha Build")
                    page.locator("#bulkMaxWorkersInput").fill("2")
                    page.locator("#workspaceBuildStartButton").click()
                    wait_for_text(
                        page,
                        "#alertStack",
                        "전체 문제 팩 빌드 완료",
                        timeout=30_000,
                    )
                    self.assert_no_browser_errors()

    def test_pack_build_is_blocked_after_full_test_failure(self) -> None:
        """패키지 빌드 차단 이후 전체 테스트 실패 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        pack_build_called = {"value": False}

        def fail_if_pack_build(route):
            """실패 조건 패키지 빌드 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
            """
            pack_build_called["value"] = True
            route.fulfill(json={"jobId": "unexpected", "status": "running"})

        with isolated_runtime("alj-problem-studio-pack-gate-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha Gate", "E2E")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                jobs: dict[str, dict] = {}
                route_studio_jobs(page, jobs)
                failed_check = {
                    "problemId": "alpha",
                    "passed": False,
                    "cases": {
                        "profiles": [{"name": "hidden", "caseCount": 1}],
                    },
                    "tools": {"labels": {"checker": "checker"}},
                    "validation": {
                        "problemId": "alpha",
                        "profileCount": 1,
                        "caseCount": 1,
                        "profiles": [{"name": "hidden", "caseCount": 1}],
                    },
                    "verification": {
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
                                "runId": "gate-run",
                                "metrics": {},
                                "cases": [],
                            }
                        ],
                    },
                }

                def queue_failed_check(route):
                    """큐 실패한 검사 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                    Args:
                        route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
                    """
                    job = completed_studio_job(
                        "full-check-gate",
                        "full-check",
                        "전체 테스트 · alpha",
                        failed_check,
                        last_log="전체 테스트 실패",
                    )
                    jobs[job["jobId"]] = job
                    route.fulfill(json=job)

                page.route("**/api/problems/*/checks/jobs", queue_failed_check)
                page.route("**/api/problems/*/packs/build", fail_if_pack_build)

                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="build"]').click()
                page.locator("#packButton").click()

                wait_for_text(page, "#alertStack", "전체 테스트를 통과하지 못해")
                self.assertFalse(pack_build_called["value"])
                self.assertFalse(page.locator("#buildDashboardDownloadLink").is_visible())
                self.assert_no_browser_errors()

    def test_problem_studio_pack_installs_and_runs_in_judge(self) -> None:
        """문제 스튜디오 패키지 설치 및 실행 채점기 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        archive_holder: dict[str, Path] = {}

        def build_and_capture(*args, **kwargs) -> dict:
            """빌드 및 캡처 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
            result = fake_build_runnable_pack(*args, **kwargs)
            archive_holder["path"] = Path(result["archivePath"])
            return result

        with isolated_runtime("alj-problem-studio-handoff-e2e-") as (_directory, workspace):
            create_problem(workspace, "bridge", "Bridge Pack", "E2E")
            patches = [
                patch(
                    "problem_studio.web.routes.tools.compile_problem_tools",
                    fake_compile_problem_tools,
                ),
                patch("problem_studio.web.routes.cases.validate_all_data", fake_validate_all_data),
                patch(
                    "problem_studio.web.routes.solutions.verify_solutions",
                    fake_verify_solutions,
                ),
                patch(
                    "problem_studio.web.routes.checks.compile_problem_tools",
                    fake_compile_problem_tools,
                ),
                patch(
                    "problem_studio.web.routes.checks.validate_all_data",
                    fake_validate_all_data,
                ),
                patch(
                    "problem_studio.web.routes.checks.verify_solutions",
                    fake_verify_solutions,
                ),
                patch(
                    "problem_studio.web.routes.packs.build_problem_pack",
                    build_and_capture,
                ),
            ]
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                with run_app(create_app(workspace)) as server:
                    page = self.new_page(server.url)
                    page.goto(server.url)
                    page.locator("#newProblemButton").wait_for(state="visible")
                    page.locator('[data-tab="build"]').click()
                    click_by_text(page, "#tabActions button", "전체 테스트")
                    wait_for_text(page, "#buildDashboardTitle", "전체 테스트 통과")
                    page.locator("#packButton").click()
                    wait_for_text(page, "#buildDashboardPack", ".aljpack", timeout=30_000)
                    self.assertTrue(page.locator("#buildDashboardDownloadLink").is_visible())
                    self.assert_no_browser_errors()

            archive = archive_holder["path"]
            self.assertTrue(archive.exists())
            with isolated_runtime("alj-problem-studio-handoff-judge-e2e-") as (
                _judge_directory,
                runtime,
            ):
                install = run_judge_cli(runtime, "pack", "install", str(archive), check=True)
                self.assertIn("Installed pack:", install.stdout)
                empty_project = runtime / "empty-project"
                empty_project.mkdir()
                source = write_trivial_python_source(runtime / "answer.py")
                run = run_judge_cli(
                    runtime,
                    "--problem",
                    "bridge",
                    "--profile",
                    "hidden",
                    str(source),
                    check=True,
                    project_root=empty_project,
                )
                self.assertIn("Accepted", run.stdout)
                payload = json.loads(
                    (run_dir_from_stdout(runtime, run.stdout) / "result.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(payload["problemId"], "bridge")
                self.assertEqual(payload["status"], "accepted")

    def test_no_fake_template_problem_pack_production_e2e(self) -> None:
        """없는 가짜 템플릿 문제 패키지 운영 종단 간 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-problem-studio-real-pack-e2e-") as (_directory, workspace):
            create_problem(workspace, "realpack", "Real Pack", "E2E")
            link_testlib(workspace)
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_text(page, "#problemTitle", "Real Pack")
                page.locator('[data-tab="build"]').click()
                click_by_text(page, "#tabActions button", "전체 테스트")
                wait_for_text(page, "#buildDashboardTitle", "전체 테스트 통과", timeout=120_000)
                page.locator("#packButton").click()
                wait_for_text(page, "#buildDashboardPack", ".aljpack", timeout=120_000)
                self.assertTrue(page.locator("#buildDashboardDownloadLink").is_visible())
                self.assert_no_browser_errors()

            archives = list((workspace / "dist" / "packs").glob("basic-*.aljpack"))
            self.assertEqual(len(archives), 1)
            archive = archives[0]
            with isolated_runtime("alj-problem-studio-real-pack-judge-e2e-") as (
                _judge_directory,
                runtime,
            ):
                install = run_judge_cli(runtime, "pack", "install", str(archive), check=True)
                self.assertIn("Installed pack:", install.stdout)
                empty_project = runtime / "empty-project"
                empty_project.mkdir()
                source = runtime / "answer.py"
                source.write_text(
                    "import sys\nsys.stdout.write(sys.stdin.read())\n",
                    encoding="utf-8",
                )
                run = run_judge_cli(
                    runtime,
                    "--problem",
                    "realpack",
                    "--profile",
                    "hidden",
                    str(source),
                    check=True,
                    project_root=empty_project,
                )
                self.assertIn("Accepted", run.stdout)
                payload = json.loads(
                    (run_dir_from_stdout(runtime, run.stdout) / "result.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(payload["problemId"], "realpack")
                self.assertEqual(payload["status"], "accepted")

    def test_background_pack_job_recovers_after_reload_and_exposes_download(self) -> None:
        """백그라운드 패키지 작업 복구 이후 새로고침 및 노출 다운로드 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-problem-studio-pack-reload-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha Reload", "E2E")
            patches = [
                patch(
                    "problem_studio.web.routes.tools.compile_problem_tools",
                    fake_compile_problem_tools,
                ),
                patch("problem_studio.web.routes.cases.validate_all_data", fake_validate_all_data),
                patch(
                    "problem_studio.web.routes.solutions.verify_solutions",
                    fake_verify_solutions,
                ),
                patch(
                    "problem_studio.web.routes.checks.compile_problem_tools",
                    fake_compile_problem_tools,
                ),
                patch(
                    "problem_studio.web.routes.checks.validate_all_data",
                    fake_validate_all_data,
                ),
                patch(
                    "problem_studio.web.routes.checks.verify_solutions",
                    fake_verify_solutions,
                ),
                patch(
                    "problem_studio.web.routes.packs.build_problem_pack",
                    fake_slow_build_runnable_pack,
                ),
            ]
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                with run_app(create_app(workspace)) as server:
                    page = self.new_page(server.url)
                    page.goto(server.url)
                    page.locator("#newProblemButton").wait_for(state="visible")
                    page.locator('[data-tab="build"]').click()
                    click_by_text(page, "#tabActions button", "전체 테스트")
                    wait_for_text(page, "#buildDashboardTitle", "전체 테스트 통과")
                    page.locator("#packButton").click()
                    page.wait_for_function(
                        "() => Boolean(localStorage.getItem('problem-studio:pack-job:v1'))"
                    )

                    page.reload()
                    page.locator("#newProblemButton").wait_for(state="visible")
                    page.locator('[data-tab="build"]').click()
                    wait_for_text(page, "#globalTaskStatus", "팩 빌드 진행 중")
                    wait_for_text(page, "#buildDashboardPack", ".aljpack", timeout=60_000)
                    self.assertTrue(page.locator("#buildDashboardDownloadLink").is_visible())
                    href = page.locator("#buildDashboardDownloadLink").get_attribute("href")
                    self.assertIn("/api/problems/alpha/packs/jobs/", href or "")
                    self.assert_no_browser_errors()

    def test_pack_and_bulk_build_cancel_ui_in_browser(self) -> None:
        """패키지 및 일괄 빌드 취소 화면 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-problem-studio-cancel-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha Cancel", "E2E")
            create_problem(workspace, "beta", "Beta Cancel", "E2E")
            pack_calls = {"count": 0}
            bulk_calls = {"count": 0}

            def cancel_then_success_pack(*args, cancel_token=None, **kwargs) -> dict:
                """취소 성공 패키지 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Args:
                    args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                    cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.
                    kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

                Returns:
                    dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
                """
                pack_calls["count"] += 1
                if pack_calls["count"] == 1:
                    return fake_cancellable_slow_build_runnable_pack(
                        *args,
                        cancel_token=cancel_token,
                        **kwargs,
                    )
                return fake_build_runnable_pack(*args, cancel_token=cancel_token, **kwargs)

            def cancel_then_success_bulk(*args, cancel_token=None, **kwargs) -> dict:
                """취소 성공 일괄 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Args:
                    args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                    cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.
                    kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

                Returns:
                    dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
                """
                bulk_calls["count"] += 1
                if bulk_calls["count"] == 1:
                    return fake_cancellable_slow_bulk_build(
                        *args,
                        cancel_token=cancel_token,
                        **kwargs,
                    )
                return fake_bulk_build(*args, cancel_token=cancel_token, **kwargs)

            patches = [
                patch(
                    "problem_studio.web.routes.tools.compile_problem_tools",
                    fake_compile_problem_tools,
                ),
                patch("problem_studio.web.routes.cases.validate_all_data", fake_validate_all_data),
                patch(
                    "problem_studio.web.routes.solutions.verify_solutions",
                    fake_verify_solutions,
                ),
                patch(
                    "problem_studio.web.routes.checks.compile_problem_tools",
                    fake_compile_problem_tools,
                ),
                patch(
                    "problem_studio.web.routes.checks.validate_all_data",
                    fake_validate_all_data,
                ),
                patch(
                    "problem_studio.web.routes.checks.verify_solutions",
                    fake_verify_solutions,
                ),
                patch(
                    "problem_studio.web.routes.packs.build_problem_pack",
                    cancel_then_success_pack,
                ),
                patch(
                    "problem_studio.web.routes.bulk.build_all_problem_packs",
                    cancel_then_success_bulk,
                ),
            ]
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                with run_app(create_app(workspace)) as server:
                    page = self.new_page(server.url)

                    def close_alerts() -> None:
                        """닫기 알림 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다."""
                        page.locator("#alertStack").evaluate(
                            "node => node.querySelectorAll('.app-alert')"
                            ".forEach((item) => item.remove())"
                        )

                    page.goto(server.url)
                    page.locator("#newProblemButton").wait_for(state="visible")
                    page.locator('[data-tab="build"]').click()
                    click_by_text(page, "#tabActions button", "전체 테스트")
                    wait_for_text(page, "#buildDashboardTitle", "전체 테스트 통과")
                    close_alerts()

                    page.locator("#packButton").click()
                    wait_for_text(page, "#globalTaskStatus", "팩 빌드 진행 중")
                    close_alerts()
                    page.locator("[data-cancel-pack-job]").evaluate("button => button.click()")
                    wait_for_text(page, "#alertStack", "팩 빌드를 취소했습니다.", timeout=30_000)
                    self.assertFalse(page.locator("[data-cancel-pack-job]").is_visible())
                    close_alerts()
                    page.locator("#packButton").click()
                    wait_for_text(page, "#alertStack", "팩 빌드 완료", timeout=30_000)
                    self.assertFalse(page.locator("[data-cancel-pack-job]").is_visible())
                    close_alerts()

                    page.locator("#workspaceBuildAllButton").click()
                    page.locator("#workspaceBuildModal").wait_for(state="visible")
                    page.locator("#workspaceBuildStartButton").click()
                    wait_for_text(page, "#globalTaskStatus", "전체 문제 빌드 진행 중")
                    close_alerts()
                    page.locator("[data-cancel-bulk-job]").evaluate("button => button.click()")
                    wait_for_text(
                        page,
                        "#alertStack",
                        "전체 문제 테스트/팩 빌드를 취소했습니다.",
                        timeout=30_000,
                    )
                    self.assertFalse(page.locator("[data-cancel-bulk-job]").is_visible())
                    close_alerts()
                    page.locator("#workspaceBuildAllButton").click()
                    page.locator("#workspaceBuildModal").wait_for(state="visible")
                    page.locator("#workspaceBuildStartButton").click()
                    wait_for_text(
                        page,
                        "#alertStack",
                        "전체 문제 팩 빌드 완료",
                        timeout=30_000,
                    )
                    self.assertFalse(page.locator("[data-cancel-bulk-job]").is_visible())
                    self.assertGreaterEqual(pack_calls["count"], 2)
                    self.assertGreaterEqual(bulk_calls["count"], 2)
                    self.assert_no_browser_errors()

    def test_stale_background_pack_job_can_be_dismissed_in_browser(self) -> None:
        """오래된 백그라운드 패키지 작업 가능 정리 브라우저 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-problem-studio-stale-pack-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha Stale", "E2E")
            dismissed = {"value": False}
            stale_job = {
                "jobId": "stale-job",
                "kind": "pack-build",
                "title": "팩 빌드 · alpha",
                "problemId": "alpha",
                "status": "stale",
                "previousStatus": "succeeded",
                "stale": True,
                "result": None,
                "error": None,
                "createdAt": "2026-05-22T00:00:00+00:00",
                "updatedAt": "2026-05-22T00:00:01+00:00",
                "expiresAt": "2026-05-22T00:00:01+00:00",
            }

            def stale_job_route(route):
                """오래된 작업 라우트 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Args:
                    route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
                """
                if route.request.method == "DELETE":
                    dismissed["value"] = True
                    route.fulfill(json={"dismissed": True, "jobId": "stale-job"})
                    return
                route.fulfill(json=stale_job)

            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.route("**/api/problems/alpha/packs/jobs/stale-job", stale_job_route)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.evaluate(
                    """() => localStorage.setItem(
                        "problem-studio:pack-job:v1",
                        JSON.stringify({
                            jobId: "stale-job",
                            problemId: "alpha",
                            packId: "basic",
                            outputDir: "dist/packs"
                        })
                    )"""
                )
                page.reload()
                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_text(page, "#globalTaskStatus", "만료된 팩 빌드", timeout=30_000)
                page.locator("[data-dismiss-stale-pack-job]").click()
                page.wait_for_function(
                    "() => !document.querySelector('[data-dismiss-stale-pack-job]')"
                )
                self.assertTrue(dismissed["value"])
                self.assert_no_browser_errors()

    def test_missing_background_pack_job_is_shown_as_stale_after_reload(self) -> None:
        """누락 백그라운드 패키지 작업 표시 오래된 이후 새로고침 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-problem-studio-missing-pack-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha Missing", "E2E")

            def missing_job_route(route):
                """누락 작업 라우트 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Args:
                    route (Any): 브라우저 라우팅 콜백에서 받은 요청 객체입니다.
                """
                route.fulfill(status=404, json={"detail": "pack build job not found"})

            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.route("**/api/problems/alpha/packs/jobs/missing-job", missing_job_route)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.evaluate(
                    """() => localStorage.setItem(
                        "problem-studio:pack-job:v1",
                        JSON.stringify({
                            jobId: "missing-job",
                            problemId: "alpha",
                            packId: "basic",
                            outputDir: "dist/packs"
                        })
                    )"""
                )
                page.reload()
                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_text(page, "#globalTaskStatus", "만료된 팩 빌드", timeout=30_000)
                page.locator("[data-dismiss-stale-pack-job]").click()
                page.wait_for_function(
                    "() => !document.querySelector('[data-dismiss-stale-pack-job]')"
                )
                unexpected_errors = [
                    error
                    for error in self.browser_errors
                    if "missing-job" not in error and "404 (Not Found)" not in error
                ]
                self.assertEqual(unexpected_errors, [])

    def test_dirty_file_is_auto_saved_before_actions(self) -> None:
        """변경 파일 파일 자동 저장 전에 동작 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-problem-studio-dirty-autosave-e2e-") as (_directory, root):
            workspace = root / "workspace"
            workspace.mkdir()
            git(workspace, "init")
            git(workspace, "checkout", "-b", "feature/e2e")
            git(workspace, "config", "user.email", "studio@example.com")
            git(workspace, "config", "user.name", "Problem Studio")
            create_problem(workspace, "alpha", "Alpha Dirty", "E2E")
            git(workspace, "add", "problems")
            git(workspace, "commit", "-m", "initial")
            patches = [
                patch(
                    "problem_studio.web.routes.tools.compile_problem_tools",
                    fake_compile_problem_tools,
                ),
                patch("problem_studio.web.routes.cases.validate_all_data", fake_validate_all_data),
                patch(
                    "problem_studio.web.routes.solutions.verify_solutions",
                    fake_verify_solutions,
                ),
                patch(
                    "problem_studio.web.routes.checks.compile_problem_tools",
                    fake_compile_problem_tools,
                ),
                patch(
                    "problem_studio.web.routes.checks.validate_all_data",
                    fake_validate_all_data,
                ),
                patch(
                    "problem_studio.web.routes.checks.verify_solutions",
                    fake_verify_solutions,
                ),
                patch(
                    "problem_studio.web.routes.packs.build_problem_pack",
                    fake_build_problem_pack,
                ),
                patch("problem_studio.web.routes.bulk.build_all_problem_packs", fake_bulk_build),
            ]
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                with run_app(create_app(workspace)) as server:
                    page = self.new_page(server.url)
                    page.goto(server.url)
                    page.locator("#newProblemButton").wait_for(state="visible")
                    page.locator('[data-tab="generator"]').click()
                    wait_for_studio_file_ready(page, "generator/cases.yml")
                    set_studio_editor_value(
                        page,
                        "profiles:\n"
                        "  hidden:\n"
                        "    cases:\n"
                        "      - name: cases-save\n"
                        "        type: fixed\n"
                        "        content: |\n"
                        "          1\n",
                    )
                    wait_for_text(page, "#fileStatus", "수정됨")

                    click_by_text(page, "#tabActions button", "Cases 검사")
                    wait_for_text(page, "#lastRunTitle", "Cases 검사 완료")
                    cases_path = workspace / "problems" / "alpha" / "generator" / "cases.yml"
                    self.assertIn("cases-save", cases_path.read_text(encoding="utf-8"))

                    wait_for_studio_file_ready(page, "generator/cases.yml")
                    set_studio_editor_value(
                        page,
                        "profiles:\n  hidden:\n    cases:\n      - name: pack-save\n",
                    )
                    page.locator("#workspaceBuildAllButton").click()
                    page.locator("#workspaceBuildModal").wait_for(state="visible")
                    page.locator("#workspaceBuildStartButton").click()
                    wait_for_text(page, "#alertStack", "전체 문제 팩 빌드 완료")
                    self.assertIn("pack-save", cases_path.read_text(encoding="utf-8"))

                    self.assert_no_browser_errors()

    def test_bulk_build_deselect_zero_selection_and_partial_failure_ui(self) -> None:
        """일괄 빌드 선택 해제 0개 선택 및 부분 실패 화면 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-problem-studio-bulk-gap-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha Bulk", "E2E")
            create_problem(workspace, "beta", "Beta Bulk", "E2E")
            with patch(
                "problem_studio.web.routes.bulk.build_all_problem_packs",
                fake_bulk_build_partial,
            ):
                with run_app(create_app(workspace)) as server:
                    page = self.new_page(server.url)
                    page.goto(server.url)
                    page.locator("#newProblemButton").wait_for(state="visible")
                    page.locator("#workspaceBuildAllButton").click()
                    page.locator("#workspaceBuildModal").wait_for(state="visible")
                    for checkbox in page.locator("[data-bulk-problem]").all():
                        checkbox.uncheck()
                    wait_for_text(page, "#workspaceBuildStartButton", "문제를 선택하세요")
                    self.assertTrue(page.locator("#workspaceBuildStartButton").is_disabled())

                    page.locator("#bulkSelectAllButton").click()
                    wait_for_text(page, "#workspaceBuildStartButton", "선택한 2개 문제")
                    page.locator("#workspaceBuildStartButton").click()
                    wait_for_text(page, "#lastRunTitle", "전체 문제 테스트/팩 빌드 실패")
                    wait_for_text(page, "#alertStack", "1개 문제 실패")
                    self.assert_no_browser_errors()
