from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JudgeProblemPickerUiContractTest(unittest.TestCase):
    def test_mobile_picker_has_accessible_search_and_live_results(self) -> None:
        page = (ROOT / "judge/web/static/index.html").read_text(encoding="utf-8")
        problems = (ROOT / "judge/web/static/app/problems.js").read_text(encoding="utf-8")
        events = (ROOT / "judge/web/static/app/events.js").read_text(encoding="utf-8")
        modal = (ROOT / "judge/web/static/app/modal.js").read_text(encoding="utf-8")

        self.assertIn('id="problemPickerModal"', page)
        self.assertIn('id="problemPickerSearchInput"', page)
        self.assertIn('id="problemPickerResults"', page)
        self.assertIn('role="status"', page)
        self.assertIn("data-modal-autofocus", page)
        self.assertIn('window.matchMedia("(max-width: 900px)")', problems)
        self.assertIn('app.on("problemJumpButton", "click", app.openProblemNavigation)', events)
        self.assertIn('app.optional("problemPickerModal")?.classList.add("hidden")', modal)

    def test_problem_renderers_use_selected_context_action_and_shared_folder_dialog(self) -> None:
        page = (ROOT / "judge/web/static/index.html").read_text(encoding="utf-8")
        problems = (ROOT / "judge/web/static/app/problems.js").read_text(encoding="utf-8")

        self.assertIn("function filterProblems(", problems)
        self.assertIn("function chooseProblem(", problems)
        self.assertIn("function renderProblemPicker(", problems)
        self.assertIn('className = "problem-folder-move-action"', problems)
        self.assertIn("problem.problemId === state.selectedProblem", problems)
        self.assertNotIn("createProblemFolderMoveSelect", problems)
        self.assertNotIn("폴더 선택으로 이동 가능", problems)
        self.assertIn('method: "PATCH"', problems)
        self.assertIn("focusEditor: picker", problems)
        self.assertIn('id="problemFolderMoveModal"', page)
        self.assertIn('id="problemFolderMoveSelect"', page)
        self.assertIn('id="problemFolderMoveConfirmButton"', page)

    def test_folder_management_is_hidden_behind_ellipsis_menu(self) -> None:
        problems = (ROOT / "judge/web/static/app/problems.js").read_text(encoding="utf-8")
        events = (ROOT / "judge/web/static/app/events.js").read_text(encoding="utf-8")
        layout = (ROOT / "judge/web/static/styles/layout.css").read_text(encoding="utf-8")

        self.assertIn('class="folder-menu-trigger"', problems)
        self.assertIn('class="folder-actions-popover hidden"', problems)
        self.assertIn("data-folder-rename=", problems)
        self.assertIn("data-folder-delete=", problems)
        self.assertIn("async function renameProblemFolder(folder)", problems)
        self.assertIn('method: "PATCH"', problems)
        self.assertIn("app.renameProblemFolder(renameFolder)", events)
        self.assertIn(".folder-actions-popover", layout)

    def test_picker_styles_bound_the_list_and_mobile_touch_targets(self) -> None:
        layout = (ROOT / "judge/web/static/styles/layout.css").read_text(encoding="utf-8")
        modal_styles = (ROOT / "judge/web/static/styles/modals.css").read_text(encoding="utf-8")
        responsive = (ROOT / "judge/web/static/styles/responsive.css").read_text(encoding="utf-8")

        self.assertIn(".problem-picker-list", modal_styles)
        self.assertIn("overflow-y: auto", modal_styles)
        self.assertIn(".problem-folder-move-action", responsive)
        self.assertIn(".problem-item-row.has-folder-action", layout)
        self.assertNotIn(".problem-folder-move-select", layout + responsive)
        action_style = layout.split(".problem-folder-move-action {", 1)[1].split("}", 1)[0]
        self.assertIn("opacity: 1", action_style)
        self.assertIn("pointer-events: auto", action_style)
        self.assertIn("min-height: 44px", responsive)

    def test_narrow_layout_shrinks_and_tablet_problem_list_keeps_own_scroll(self) -> None:
        responsive = (ROOT / "judge/web/static/styles/responsive.css").read_text(encoding="utf-8")

        self.assertIn("grid-template-columns: minmax(0, 1fr)", responsive)
        self.assertIn(".sidebar {", responsive)
        self.assertIn("min-width: 0", responsive)
        self.assertIn("max-height: min(55dvh, 520px)", responsive)
        self.assertIn("overflow-y: auto", responsive)
        self.assertIn("@media (max-width: 560px)", responsive)
        self.assertIn("max-height: none", responsive)


if __name__ == "__main__":
    unittest.main()
