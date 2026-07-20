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

    def test_empty_workspace_prioritizes_first_problem_onboarding(self) -> None:
        """문제가 없는 임시 workspace는 제작 폼 대신 시작 경로만 보여야 합니다."""
        with isolated_runtime("alj-problem-studio-empty-e2e-") as (_directory, workspace):
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)

                empty_state = page.locator("#workspaceEmptyState")
                empty_state.wait_for(state="visible")
                wait_for_text(page, "#workspaceEmptyTitle", "첫 문제를 만들어 시작하세요")
                self.assertEqual(
                    page.locator("#workspaceEmptyState").get_attribute("aria-hidden"),
                    "false",
                )
                self.assertEqual(
                    page.locator("#problemAuthoringWorkspace").get_attribute("aria-hidden"),
                    "true",
                )
                self.assertFalse(page.locator("#metadataForm").is_visible())
                self.assertFalse(page.locator("#saveFileButton").is_visible())
                self.assertFalse(page.locator("#workspaceBuildAllButton").is_visible())
                self.assertTrue(page.locator("#emptyCreateProblemButton").is_visible())
                self.assertTrue(page.locator("#emptyAddRepositoryButton").is_visible())
                self.assertTrue(page.locator("#emptyOpenRepositoryButton").is_visible())

                page.locator("#emptyCreateProblemButton").click()
                page.locator("#newProblemModal").wait_for(state="visible")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "newProblemId",
                )
                page.locator("#newProblemId").fill("empty-e2e")
                page.locator("#newProblemTitle").fill("Empty State E2E")
                page.locator("#createProblemButton").click()

                page.locator("#workspaceEmptyState").wait_for(state="hidden")
                wait_for_text(page, "#problemTitle", "Empty State E2E")
                self.assertEqual(
                    page.locator("#problemAuthoringWorkspace").get_attribute("aria-hidden"),
                    "false",
                )
                self.assertTrue(page.locator("#saveFileButton").is_visible())
                self.assertTrue((workspace / "problems" / "empty-e2e").is_dir())
                self.assert_no_browser_errors()

    def test_modals_have_accessible_names_and_keyboard_focus_contract(self) -> None:
        """모달 이름·설명, focus trap, Escape 닫기와 trigger 복귀를 검증합니다."""
        with isolated_runtime("alj-problem-studio-modal-a11y-e2e-") as (
            _directory,
            workspace,
        ):
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#workspaceEmptyState").wait_for(state="visible")

                contracts = page.evaluate(
                    r"""() => [...document.querySelectorAll(".modal, #editorSettingsPanel")].map((dialog) => {
                        const labelledBy = dialog.getAttribute("aria-labelledby") || "";
                        const describedBy = dialog.getAttribute("aria-describedby") || "";
                        return {
                            id: dialog.id,
                            labelledBy,
                            headingExists: Boolean(labelledBy && document.getElementById(labelledBy)),
                            descriptionsExist: describedBy
                                .split(/\s+/)
                                .filter(Boolean)
                                .every((id) => Boolean(document.getElementById(id))),
                        };
                    })"""
                )
                self.assertTrue(contracts)
                self.assertTrue(all(item["headingExists"] for item in contracts), contracts)
                self.assertTrue(all(item["descriptionsExist"] for item in contracts), contracts)
                heading_ids = [item["labelledBy"] for item in contracts]
                self.assertEqual(len(heading_ids), len(set(heading_ids)))

                first_problem = page.locator("#emptyCreateProblemButton")
                first_problem.click()
                page.locator("#newProblemModal").wait_for(state="visible")
                self.assertEqual(page.evaluate("() => document.activeElement?.id"), "newProblemId")

                close_button = page.locator("#newProblemModal [data-modal-close]")
                close_button.focus()
                page.keyboard.press("Shift+Tab")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "createProblemButton",
                )
                page.keyboard.press("Tab")
                self.assertTrue(
                    page.evaluate(
                        """() => document.activeElement?.matches(
                            "#newProblemModal [data-modal-close]"
                        )"""
                    )
                )
                page.keyboard.press("Escape")
                page.locator("#newProblemModal").wait_for(state="hidden")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "emptyCreateProblemButton",
                )

                page.locator("#emptyAddRepositoryButton").click()
                page.locator("#repositoryModal").wait_for(state="visible")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "repositoryUrlInput",
                )
                page.keyboard.press("Escape")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "emptyAddRepositoryButton",
                )

                page.locator("#emptyOpenRepositoryButton").click()
                page.locator("#repositoryOpenModal").wait_for(state="visible")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "repositoryOpenCloneButton",
                )
                page.keyboard.press("Escape")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "emptyOpenRepositoryButton",
                )

                page.locator("#emptyCreateProblemButton").click()
                page.locator("#newProblemId").fill("vim-modal-a11y")
                page.locator("#newProblemTitle").fill("Vim Modal Accessibility")
                page.locator("#createProblemButton").click()
                page.locator('[data-tab="solutions"]').click()
                click_by_text(page, "#tabActions button", "새 솔루션")
                page.locator("#solutionCreateModal").wait_for(state="visible")
                page.locator("#solutionCreateModal [data-editor-mode='vim']").click()
                modal_editor = page.locator("#solutionCreateModal .source-modal-codemirror")
                modal_editor.click()
                page.keyboard.press("Escape")
                self.assertTrue(page.locator("#solutionCreateModal").is_visible())
                page.keyboard.press("Escape")
                page.locator("#solutionCreateModal").wait_for(state="hidden")
                self.assert_no_browser_errors()

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

    def test_unified_unsaved_changes_guard_preserves_every_authoring_surface(self) -> None:
        """파일·메타데이터·솔루션 모달이 동일한 저장/버리기/취소 계약을 사용합니다."""
        with isolated_runtime("alj-problem-studio-unsaved-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha Guard", "E2E")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                self.assert_no_browser_errors()
                wait_for_value(page, "#metadataTitle", "Alpha Guard")

                page.locator("#metadataTitle").fill("Unsaved metadata")
                page.locator('[data-tab="generator"]').click()
                page.locator("#unsavedChangesModal").wait_for(state="visible")
                wait_for_text(page, "#unsavedChangesSources", "문제 정보")
                page.locator("#unsavedChangesCancelButton").click()
                page.locator("#unsavedChangesModal").wait_for(state="hidden")
                self.assertEqual(page.locator("#metadataTitle").input_value(), "Unsaved metadata")
                self.assertEqual(
                    (workspace / "problems" / "alpha" / "problem.json")
                    .read_text(encoding="utf-8")
                    .count("Unsaved metadata"),
                    0,
                )

                page.locator('[data-tab="generator"]').click()
                page.locator("#unsavedChangesDiscardButton").click()
                wait_for_studio_file_ready(page, "generator/cases.yml")
                self.assertEqual(page.locator("#metadataTitle").input_value(), "Alpha Guard")

                saved_cases = studio_editor_value(page)
                changed_cases = f"{saved_cases.rstrip()}\n# guarded-change\n"
                set_studio_editor_value(page, changed_cases)
                wait_for_text(page, "#fileStatus", "수정됨")
                page.locator('[data-tab="checker"]').click()
                page.locator("#unsavedChangesModal").wait_for(state="visible")
                wait_for_text(page, "#unsavedChangesSources", "generator/cases.yml")
                page.locator("#unsavedChangesSaveButton").click()
                wait_for_studio_file_ready(page, "checker/judge.cpp")
                self.assertIn(
                    "guarded-change",
                    (workspace / "problems" / "alpha" / "generator" / "cases.yml").read_text(
                        encoding="utf-8"
                    ),
                )

                page.locator('[data-tab="info"]').click()
                wait_for_studio_file_ready(page, "problem.json")
                set_studio_editor_value(page, f"{studio_editor_value(page)}\n ")
                page.locator("#metadataTitle").fill("Conflicting metadata")
                page.locator('[data-tab="solutions"]').click()
                page.locator("#unsavedChangesModal").wait_for(state="visible")
                self.assertTrue(page.locator("#unsavedChangesSaveButton").is_disabled())
                wait_for_text(page, "#unsavedChangesConflict", "자동 병합하지 않습니다")
                page.locator("#unsavedChangesCancelButton").click()
                self.assertEqual(
                    page.locator("#metadataTitle").input_value(),
                    "Conflicting metadata",
                )

                page.locator('[data-tab="solutions"]').click()
                page.locator("#unsavedChangesDiscardButton").click()
                click_by_text(page, "#tabActions button", "새 솔루션")
                page.locator("#solutionCreateModal").wait_for(state="visible")
                page.locator("#solutionCreateName").fill("guarded_solution")
                page.locator("#solutionCreateModal [data-modal-close]").click()
                page.locator("#unsavedChangesModal").wait_for(state="visible")
                wait_for_text(page, "#unsavedChangesSources", "새 솔루션")
                page.locator("#unsavedChangesCancelButton").click()
                self.assertTrue(page.locator("#solutionCreateModal").is_visible())
                self.assertEqual(
                    page.locator("#solutionCreateName").input_value(),
                    "guarded_solution",
                )
                page.locator("#solutionCreateModal [data-modal-close]").click()
                page.locator("#unsavedChangesDiscardButton").click()
                page.locator("#solutionCreateModal").wait_for(state="hidden")
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
                    (1366, 768),
                    (1280, 900),
                    (1200, 768),
                    (1199, 768),
                    (1180, 900),
                    (1080, 900),
                    (768, 900),
                    (390, 844),
                ]:
                    page = self.new_page(server.url, width=width, height=height)
                    page.goto(server.url)
                    page.locator("#studioSidebar").wait_for(state="attached")
                    assert_no_horizontal_overflow(self, page, label=f"initial at {width}px")
                    if width <= 1199:
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

    def test_problem_sidebar_scroll_and_surface_accessibility_contract(self) -> None:
        """100개 문제 목록의 독립 스크롤과 1200/1199 surface 경계를 검증합니다."""
        with isolated_runtime("alj-problem-studio-sidebar-e2e-") as (_directory, workspace):
            for index in range(100):
                create_problem(
                    workspace,
                    f"problem-{index:03d}",
                    f"Problem {index:03d}",
                    f"Folder {index // 20}",
                )
            with run_app(create_app(workspace)) as server:
                desktop = self.new_page(server.url, width=1366, height=768)
                desktop.goto(server.url)
                wait_for_text(desktop, "#problemList", "problem-099")
                self.assertTrue(desktop.locator("#studioSidebar").is_visible())
                self.assertEqual(
                    desktop.locator("#studioSidebar").get_attribute("role"),
                    "navigation",
                )
                layout = desktop.evaluate(
                    """() => {
                        const sidebar = document.querySelector("#studioSidebar");
                        const list = document.querySelector("#problemList");
                        sidebar.scrollTop = 1000;
                        return {
                            sidebarOverflow: getComputedStyle(sidebar).overflowY,
                            sidebarScrollTop: sidebar.scrollTop,
                            listOverflow: getComputedStyle(list).overflowY,
                            listClientHeight: list.clientHeight,
                            listScrollHeight: list.scrollHeight,
                        };
                    }"""
                )
                self.assertEqual(layout["sidebarOverflow"], "hidden")
                self.assertEqual(layout["sidebarScrollTop"], 0)
                self.assertEqual(layout["listOverflow"], "auto")
                self.assertGreaterEqual(layout["listClientHeight"], 80)
                self.assertGreater(layout["listScrollHeight"], layout["listClientHeight"])

                first_visible_script = """() => {
                    const list = document.querySelector("#problemList");
                    return [...list.querySelectorAll("[data-problem-id]")]
                        .find((item) => item.offsetTop + item.offsetHeight > list.scrollTop)
                        ?.dataset.problemId || "";
                }"""
                desktop.evaluate(
                    """() => {
                        const list = document.querySelector("#problemList");
                        list.scrollTop = Math.floor((list.scrollHeight - list.clientHeight) * 0.55);
                    }"""
                )
                before_filter = desktop.evaluate(first_visible_script)
                desktop.locator("#problemFilterInput").fill("problem")
                desktop.wait_for_timeout(100)
                self.assertEqual(desktop.evaluate(first_visible_script), before_filter)
                desktop.locator("#problemFilterInput").fill("")
                desktop.wait_for_timeout(100)
                self.assertEqual(desktop.evaluate(first_visible_script), before_filter)

                desktop.locator('[data-problem-id="problem-099"]').click()
                wait_for_text(desktop, "#problemTitle", "Problem 099")
                selected_visibility = desktop.evaluate(
                    """() => {
                            const list = document.querySelector("#problemList").getBoundingClientRect();
                            const selected = document.querySelector("#problemList .list-item.active")
                                .getBoundingClientRect();
                            return {
                                visible: selected.top >= list.top && selected.bottom <= list.bottom,
                                listTop: list.top,
                                listBottom: list.bottom,
                                selectedTop: selected.top,
                                selectedBottom: selected.bottom,
                                scrollTop: document.querySelector("#problemList").scrollTop,
                                selectedId: document.querySelector("#problemList .list-item.active")
                                    .dataset.problemId,
                            };
                        }"""
                )
                self.assertTrue(
                    selected_visibility["visible"],
                    selected_visibility,
                )

                boundary = self.new_page(server.url, width=1200, height=720)
                boundary.goto(server.url)
                boundary.locator("#newProblemButton").wait_for(state="visible")
                self.assertEqual(
                    boundary.locator("#studioSidebar").get_attribute("role"), "navigation"
                )
                boundary.locator("#jobCenterButton").click()
                self.assertEqual(
                    boundary.locator("#jobCenterDrawer").get_attribute("role"),
                    "complementary",
                )
                self.assertIsNone(boundary.locator(".shell").get_attribute("inert"))
                boundary.keyboard.press("Escape")
                boundary.locator("#jobCenterDrawer").wait_for(state="hidden")

                compact = self.new_page(server.url, width=1199, height=720)
                compact.goto(server.url)
                compact.locator("#sidebarToggle").click()
                self.assertEqual(compact.locator("#studioSidebar").get_attribute("role"), "dialog")
                self.assertEqual(
                    compact.locator("#studioSidebar").get_attribute("aria-modal"), "true"
                )
                self.assertEqual(compact.locator(".workspace").get_attribute("inert"), "")
                self.assertEqual(
                    compact.evaluate("() => document.activeElement?.id"), "problemFilterInput"
                )
                compact.locator("#problemList .list-item").last.focus()
                compact.keyboard.press("Tab")
                self.assertEqual(
                    compact.evaluate("() => document.activeElement?.id"), "sidebarClose"
                )
                compact.keyboard.press("Escape")
                compact.wait_for_function(
                    "() => !document.body.classList.contains('sidebar-open')"
                )
                self.assertEqual(
                    compact.evaluate("() => document.activeElement?.id"), "sidebarToggle"
                )

                compact.locator("#jobCenterButton").click()
                drawer = compact.locator("#jobCenterDrawer")
                drawer.wait_for(state="visible")
                self.assertEqual(drawer.get_attribute("role"), "dialog")
                self.assertEqual(drawer.get_attribute("aria-modal"), "true")
                self.assertEqual(compact.locator(".shell").get_attribute("inert"), "")
                self.assertEqual(
                    compact.evaluate("() => document.activeElement?.id"), "jobCenterCloseButton"
                )
                compact.locator("#jobCenterClearButton").focus()
                compact.keyboard.press("Tab")
                self.assertEqual(
                    compact.evaluate("() => document.activeElement?.id"), "jobCenterCloseButton"
                )
                compact.keyboard.press("Escape")
                drawer.wait_for(state="hidden")
                self.assertEqual(
                    compact.evaluate("() => document.activeElement?.id"), "jobCenterButton"
                )
                self.assertIsNone(compact.locator(".shell").get_attribute("inert"))

                zoomed = self.new_page(server.url, width=960, height=576)
                zoomed.goto(server.url)
                zoomed.locator("#sidebarToggle").click()
                self.assertGreaterEqual(
                    zoomed.locator("#problemList").evaluate("el => el.clientHeight"), 80
                )
                assert_no_horizontal_overflow(self, zoomed, label="125% zoom equivalent")
                self.assert_no_browser_errors()

    def test_authoring_tabs_roving_keyboard_and_path_disclosure(self) -> None:
        """작성 탭 roving keyboard와 절대 경로 축약 disclosure를 검증합니다."""
        with isolated_runtime("alj-problem-studio-tabs-e2e-") as (_directory, workspace):
            create_problem(workspace, "alpha", "Alpha Tabs", "E2E")
            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url, width=1366, height=768)
                page.goto(server.url)
                wait_for_value(page, "#metadataTitle", "Alpha Tabs")
                info = page.locator("#authoringTab-info")
                generator = page.locator("#authoringTab-generator")
                self.assertEqual(info.get_attribute("tabindex"), "0")
                self.assertEqual(generator.get_attribute("tabindex"), "-1")

                info.focus()
                page.keyboard.press("ArrowRight")
                page.wait_for_function(
                    "() => document.querySelector('#authoringTab-generator')?.getAttribute('aria-selected') === 'true'"
                )
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"), "authoringTab-generator"
                )
                self.assertEqual(generator.get_attribute("tabindex"), "0")
                self.assertEqual(
                    page.locator("#authoringTabPanel").get_attribute("aria-labelledby"),
                    "authoringTab-generator",
                )

                page.keyboard.press("End")
                page.wait_for_function(
                    "() => document.querySelector('#authoringTab-build')?.getAttribute('aria-selected') === 'true'"
                )
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"), "authoringTab-build"
                )
                page.keyboard.press("Home")
                page.wait_for_function(
                    "() => document.querySelector('#authoringTab-info')?.getAttribute('aria-selected') === 'true'"
                )

                page.locator("#metadataTitle").fill("Unsaved tab title")
                info.focus()
                page.keyboard.press("ArrowRight")
                page.locator("#unsavedChangesModal").wait_for(state="visible")
                page.locator("#unsavedChangesCancelButton").click()
                self.assertEqual(info.get_attribute("aria-selected"), "true")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"), "authoringTab-info"
                )
                self.assertEqual(page.locator("#metadataTitle").input_value(), "Unsaved tab title")

                disclosure = page.locator("#repositoryStatus .path-disclosure")
                disclosure.wait_for(state="visible")
                compact = disclosure.locator("summary").inner_text()
                self.assertTrue(compact.startswith("~") or compact.startswith("…/"), compact)
                self.assertIn(str(workspace), disclosure.locator("code").inner_text())
                self.assert_no_browser_errors()
