"""Problem Studio 문제 작성 브라우저 E2E 테스트입니다."""

from __future__ import annotations

from problem_studio.core.templates import create_problem
from problem_studio.web.app import create_app
from tests.e2e.helpers import (
    BrowserE2ETestCase,
    assert_no_overlap,
    assert_visible_in_viewport,
    click_by_text,
    create_studio_problem,
    isolated_runtime,
    run_app,
    set_studio_editor_value,
    studio_editor_value,
    wait_for_studio_file_ready,
    wait_for_text,
    wait_for_value,
)


def assert_no_horizontal_overflow(test: BrowserE2ETestCase, page, *, label: str) -> None:
    """현재 문서가 viewport보다 넓게 밀리지 않는지 확인합니다.

    Args:
        test (BrowserE2ETestCase): 검증 실패를 보고할 테스트 케이스입니다.
        page (Any): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        label (str): 실패 메시지에 포함할 화면/뷰포트 설명입니다.
    """
    overflow = page.evaluate(
        """() => ({
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
        })"""
    )
    test.assertLessEqual(
        overflow["scrollWidth"],
        overflow["clientWidth"] + 1,
        f"{label} overflowed: {overflow}",
    )


class ProblemStudioAuthoringE2ETest(BrowserE2ETestCase):
    """Problem Studio 문제 작성 브라우저 흐름을 검증합니다."""

    def test_create_problem_edit_metadata_and_save_file_in_browser(self) -> None:
        """문제 생성, 메타데이터 편집, 파일 저장 흐름을 검증합니다."""
        with isolated_runtime("alj-problem-studio-e2e-") as (_directory, workspace):
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)

                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_text(page, "#problemList", "등록된 문제가 없습니다.")
                create_studio_problem(page, "alpha", "Alpha E2E")

                wait_for_text(page, "#problemTitle", "Alpha E2E")
                wait_for_value(page, "#metadataTitle", "Alpha E2E")
                page.locator("#metadataTitle").fill("Alpha E2E Updated")
                page.get_by_role("button", name="문제 정보 저장").click()
                wait_for_text(page, "#alertStack", "문제 정보가 저장되었습니다.")
                wait_for_value(page, "#metadataTitle", "Alpha E2E Updated")

                page.locator('[data-tab="generator"]').click()
                wait_for_studio_file_ready(page, "generator/cases.yml")
                set_studio_editor_value(
                    page,
                    "profiles:\n"
                    "  hidden:\n"
                    "    cases:\n"
                    "      - name: e2e-smoke\n"
                    "        args: [1]\n",
                )
                wait_for_text(page, "#fileStatus", "수정됨")
                page.locator("#saveFileButton").click()
                wait_for_text(page, "#fileStatus", "저장됨")
                wait_for_text(page, "#alertStack", "generator/cases.yml 저장 완료")

                page.reload()
                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_text(page, "#problemTitle", "Alpha E2E Updated")
                page.locator('[data-tab="generator"]').click()
                wait_for_studio_file_ready(page, "generator/cases.yml", timeout=60_000)
                page.wait_for_function(
                    """() => {
                        const wrapper = document.querySelector("#codeEditor .studio-codemirror");
                        if (wrapper && !wrapper.CodeMirror) return false;
                        const value = wrapper?.CodeMirror
                            ? wrapper.CodeMirror.getValue()
                            : document.querySelector("#fileEditor")?.value || "";
                        return value.includes("e2e-smoke");
                    }""",
                    timeout=60_000,
                )
                self.assertIn("e2e-smoke", studio_editor_value(page))
                self.assert_no_browser_errors()

    def test_tabs_filters_stream_error_and_vim_mode_in_browser(self) -> None:
        """탭, 필터, 스트림 오류, Vim 모드 흐름을 검증합니다."""
        with isolated_runtime("alj-problem-studio-e2e-") as (_directory, workspace):
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                create_studio_problem(page, "alpha", "Alpha E2E")

                page.locator('[data-tab="generator"]').click()
                wait_for_studio_file_ready(page, "generator/cases.yml")
                wait_for_text(page, "#tabFiles", "generator/cases.yml")
                page.locator("#resourceFilterInput").fill("cases")
                wait_for_text(page, "#resourceSummary", "1/2개 표시")
                self.assertIn("generator/cases.yml", page.locator("#tabFiles").inner_text())

                click_by_text(page, "#tabActions button", "Cases 검사")
                wait_for_text(page, "#lastRunTitle", "Cases 검사 완료")
                wait_for_text(page, "#alertStack", "cases.yml OK")

                set_studio_editor_value(page, "profiles:\n  hidden:\n    cases: not-a-list\n")
                page.locator("#saveFileButton").click()
                wait_for_text(page, "#fileStatus", "저장됨")
                click_by_text(page, "#tabActions button", "Cases 검사")
                wait_for_text(page, "#lastRunTitle", "Cases 검사 실패")
                wait_for_text(page, "#lastRunSummary", "예제 preview")
                wait_for_text(page, "#lastRunSummary", "expected: profile은 mapping")
                click_by_text(page, "#tabActions button", "Sample 데이터 생성")
                wait_for_text(page, "#lastRunTitle", "sample 데이터 생성 실패")
                wait_for_text(page, "#lastRunSummary", "generator/cases.yml")

                page.locator("#editorSettingsButton").click()
                page.locator("#editorModeVim").click()
                wait_for_text(page, "#editorModeBadge", "NORMAL")
                page.reload()
                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_text(page, "#editorModeBadge", "NORMAL")
                self.assert_no_browser_errors()

    def test_textarea_fallback_editor_saves_without_codemirror(self) -> None:
        """CodeMirror 없이 textarea fallback 저장 흐름을 검증합니다."""
        with isolated_runtime("alj-problem-studio-e2e-") as (_directory, workspace):
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.route(
                    "**/static/vendor/codemirror/**/*.js*",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/javascript",
                        body="",
                    ),
                )
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                create_studio_problem(page, "fallback", "Fallback Editor")
                page.locator('[data-tab="generator"]').click()
                wait_for_studio_file_ready(page, "generator/cases.yml")

                page.locator("#fileEditor").fill(
                    "profiles:\n"
                    "  hidden:\n"
                    "    cases:\n"
                    "      - name: fallback\n"
                    "        type: fixed\n"
                    "        content: |\n"
                    "          1\n"
                )
                wait_for_text(page, "#fileStatus", "수정됨")
                page.locator("#saveFileButton").click()
                wait_for_text(page, "#fileStatus", "저장됨")
                page.reload()
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="generator"]').click()
                wait_for_studio_file_ready(page, "generator/cases.yml")
                page.wait_for_function(
                    """() => document.querySelector("#fileEditor")?.value.includes("fallback")"""
                )
                self.assertIn("fallback", page.locator("#fileEditor").input_value())
                self.assert_no_browser_errors()

    def test_problem_rename_and_delete_browser_flow(self) -> None:
        """문제 이름 변경과 삭제 브라우저 흐름을 검증합니다."""
        with isolated_runtime("alj-problem-studio-rename-delete-e2e-") as (
            _directory,
            workspace,
        ):
            create_problem(workspace, "alpha", "Alpha Rename", "E2E")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator("#metadataProblemIdInput").fill("renamed")
                page.get_by_role("button", name="문제 정보 저장").click()
                wait_for_text(page, "#alertStack", "alpha 문제 번호를 renamed로 변경")
                wait_for_value(page, "#metadataProblemIdInput", "renamed")
                wait_for_text(page, "#problemList", "renamed")

                page.reload()
                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_value(page, "#metadataProblemIdInput", "renamed")

                click_by_text(page, "#tabActions button", "문제 삭제")
                page.locator("#deleteProblemModal").wait_for(state="visible")
                page.locator("#deleteProblemConfirmInput").fill("wrong phrase")
                self.assertTrue(page.locator("#deleteProblemButton").is_disabled())
                page.locator("#deleteProblemConfirmInput").fill("확인했습니다")
                self.assertFalse(page.locator("#deleteProblemButton").is_disabled())
                page.locator("#deleteProblemButton").click()
                wait_for_text(page, "#alertStack", "renamed 문제를 삭제했습니다.")
                wait_for_text(page, "#problemList", "등록된 문제가 없습니다.")
                self.assertFalse((workspace / "problems" / "renamed").exists())
                self.assert_no_browser_errors()

    def test_textarea_vim_write_undo_and_redo_flow(self) -> None:
        """textarea Vim write, undo, redo 흐름을 검증합니다."""
        with isolated_runtime("alj-problem-studio-vim-command-e2e-") as (
            _directory,
            workspace,
        ):
            create_problem(workspace, "alpha", "Alpha Vim", "E2E")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.route(
                    "**/static/vendor/codemirror/**/*.js*",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/javascript",
                        body="",
                    ),
                )
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                page.locator('[data-tab="generator"]').click()
                wait_for_studio_file_ready(page, "generator/cases.yml")
                page.locator("#editorSettingsButton").click()
                page.locator("#editorModeVim").click()
                wait_for_text(page, "#editorModeBadge", "NORMAL")

                page.locator("#fileEditor").focus()
                page.keyboard.press("i")
                page.keyboard.type("\n# undo-target")
                page.keyboard.press("Escape")
                wait_for_text(page, "#editorModeBadge", "NORMAL")
                self.assertIn("undo-target", studio_editor_value(page))

                page.keyboard.press("u")
                self.assertNotIn("undo-target", studio_editor_value(page))
                page.keyboard.press("Control+R")
                self.assertIn("undo-target", studio_editor_value(page))

                page.keyboard.press(":")
                page.locator("#editorCommandInput").fill("w")
                page.keyboard.press("Enter")
                wait_for_text(page, "#fileStatus", "저장됨")
                cases_path = workspace / "problems" / "alpha" / "generator" / "cases.yml"
                self.assertIn("undo-target", cases_path.read_text(encoding="utf-8"))
                self.assert_no_browser_errors()

    def test_problem_studio_viewports_keep_core_controls_usable(self) -> None:
        """주요 viewport에서 핵심 컨트롤과 레이아웃을 검증합니다."""
        with isolated_runtime("alj-problem-studio-view-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha View", "E2E")
            create_problem(
                workspace,
                "beta-long-title",
                "Beta View With A Very Long Title For Narrow Screens",
                "Long Folder",
            )
            with run_app(create_app(workspace)) as server:
                for width, height in [
                    (1440, 900),
                    (1366, 900),
                    (1280, 900),
                    (1180, 900),
                    (1080, 900),
                    (768, 900),
                    (390, 844),
                ]:
                    page = self.new_page(server.url, width=width, height=height)
                    page.goto(server.url)
                    page.locator("#studioSidebar").wait_for(state="attached")
                    assert_no_horizontal_overflow(self, page, label=f"initial at {width}px")
                    if width <= 1380:
                        self.assertFalse(page.locator("#newProblemButton").is_visible())
                        self.assertEqual(page.locator("#studioSidebar").get_attribute("inert"), "")
                        self.assertEqual(
                            page.locator("#studioSidebar").get_attribute("aria-hidden"),
                            "true",
                        )
                        page.locator("#sidebarToggle").click()
                        page.locator("#newProblemButton").wait_for(state="visible")
                        self.assertIsNone(page.locator("#studioSidebar").get_attribute("inert"))
                        page.locator("#problemFilterInput").fill("beta")
                        wait_for_text(page, "#problemList", "beta-long-title")
                        self.assertNotIn("Alpha View", page.locator("#problemList").inner_text())
                        page.locator("#problemFilterInput").fill("")
                        page.locator("#newProblemButton").click()
                        assert_visible_in_viewport(
                            self,
                            page.locator("#newProblemModal .modal-content"),
                        )
                        page.keyboard.press("Escape")
                        page.locator("#newProblemModal").wait_for(state="hidden")
                        if page.evaluate(
                            """() => document.body.classList.contains("sidebar-open")"""
                        ):
                            page.mouse.click(width - 4, height // 2)
                            page.wait_for_function(
                                """() => !document.body.classList.contains("sidebar-open")"""
                            )
                            self.assertEqual(
                                page.locator("#studioSidebar").get_attribute("aria-hidden"),
                                "true",
                            )
                    else:
                        page.locator("#newProblemButton").wait_for(state="visible")
                        page.locator("#problemFilterInput").fill("beta")
                        wait_for_text(page, "#problemList", "beta-long-title")
                        self.assertNotIn("Alpha View", page.locator("#problemList").inner_text())
                        page.locator("#problemFilterInput").fill("")
                        assert_visible_in_viewport(self, page.locator("#newProblemButton"))
                        page.locator("#newProblemButton").click()
                        assert_visible_in_viewport(
                            self,
                            page.locator("#newProblemModal .modal-content"),
                        )
                        page.keyboard.press("Escape")

                    for tab in ["solutions", "build"]:
                        page.locator(f'[data-tab="{tab}"]').click()
                        page.locator(".studio-layout").wait_for(state="visible")
                        assert_no_horizontal_overflow(self, page, label=f"{tab} at {width}px")
                        global_status = page.locator("#globalTaskStatus")
                        if global_status.is_visible():
                            global_status.scroll_into_view_if_needed()
                            assert_visible_in_viewport(self, global_status)
                        page.locator("#jobCenterButton").scroll_into_view_if_needed()
                        assert_visible_in_viewport(self, page.locator("#jobCenterButton"))
                        if tab == "solutions":
                            page.locator(".solution-row").first.wait_for(state="visible")
                            status = page.locator(".solution-row .resource-status").first
                            actions = page.locator(".solution-row-actions").first
                            status.scroll_into_view_if_needed()
                            actions.scroll_into_view_if_needed()
                            assert_visible_in_viewport(self, status)
                            assert_visible_in_viewport(self, actions)
                            assert_no_overlap(self, status, actions)
                            assert_visible_in_viewport(
                                self,
                                page.locator(
                                    '[data-solution-test="solutions/main_solution.ac.cpp"]'
                                ),
                            )
                        else:
                            page.locator("#buildDashboard").scroll_into_view_if_needed()
                            assert_visible_in_viewport(self, page.locator("#buildDashboard"))

                    page.locator('[data-tab="generator"]').click()
                    page.locator("#saveFileButton").scroll_into_view_if_needed()
                    assert_visible_in_viewport(self, page.locator("#saveFileButton"))
                    page.locator("#codeEditor").scroll_into_view_if_needed()
                    assert_visible_in_viewport(self, page.locator("#codeEditor"))
                    self.assert_no_browser_errors()
