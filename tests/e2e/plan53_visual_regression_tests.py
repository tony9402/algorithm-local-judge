"""Plan 53 Judge·Problem Studio 시각 회귀 브라우저 계약입니다."""

from __future__ import annotations

import re

from judge.web.app import create_app as create_judge_app
from problem_studio.core.templates import create_problem
from problem_studio.web.app import create_app as create_studio_app
from tests.e2e.helpers import (
    BrowserE2ETestCase,
    isolated_runtime,
    judge_env,
    run_app,
    temporary_env,
    wait_for_text,
)
from tests.e2e.problem_studio_fakes import git


def route_empty_judge_secondary_data(page) -> None:
    """문제 목록 외 보조 응답이 시각 계약을 방해하지 않도록 비웁니다."""
    page.route(
        re.compile(r"/api/submissions(?:\?.*)?$"),
        lambda route: route.fulfill(
            json={
                "submissions": [],
                "page": 1,
                "pageSize": 20,
                "total": 0,
                "totalPages": 1,
            }
        ),
    )


def judge_problem(index: int, *, total: int) -> dict:
    """짧고 긴 제목이 섞인 편집 가능한 Judge 문제 응답을 만듭니다."""
    title = f"문제 {index:03d}"
    if index % 9 == 0:
        title = f"아주 긴 문제 제목 {index:03d} 텍스트 잘림과 레이아웃 겹침 검증"
    return {
        "problemId": f"mock-{index:03d}",
        "title": title,
        "version": 1,
        "defaultProfile": "full",
        "profiles": ["sample", "full"],
        "folder": "Math" if index % 2 else "Graph",
        "folderEditable": True,
        "problemCount": total,
    }


def element_overflow(page, selector: str) -> list[dict]:
    """selector에 해당하는 보이는 요소의 가로 overflow 측정값을 반환합니다."""
    return page.locator(selector).evaluate_all(
        """elements => elements
            .filter((element) => element.getClientRects().length)
            .map((element) => ({
                id: element.id || element.textContent.trim().slice(0, 40),
                clientWidth: element.clientWidth,
                scrollWidth: element.scrollWidth,
            }))"""
    )


class Plan53JudgeVisualRegressionE2ETest(BrowserE2ETestCase):
    """Judge 문제 행과 폴더 이동 surface가 실제 폭에서도 유지되는지 검증합니다."""

    def test_41_problem_rows_use_contextual_dialog_without_visual_collision(self) -> None:
        """41개 문제에서 상시 select를 없애고 dialog·drag 이동을 함께 보존합니다."""
        problems = [judge_problem(index, total=41) for index in range(1, 42)]
        with isolated_runtime("alj-plan53-judge-41-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_judge_app()) as server:
                page = self.new_page(server.url, width=1366, height=768)
                captured: dict[str, str] = {}
                folders = [
                    {"folder": "", "label": "미분류", "problemCount": 0},
                    {"folder": "Graph", "label": "Graph", "problemCount": 21},
                    {"folder": "Math", "label": "Math", "problemCount": 20},
                ]

                def update_folder(route) -> None:
                    body = route.request.post_data_json
                    problem_id = route.request.url.split("/api/problems/", 1)[1].split("/", 1)[0]
                    problem = next(item for item in problems if item["problemId"] == problem_id)
                    problem["folder"] = body["folder"]
                    captured.update(problem_id=problem_id, folder=body["folder"])
                    route.fulfill(json=problem)

                page.route("**/api/problems", lambda route: route.fulfill(json=problems))
                page.route("**/api/folders", lambda route: route.fulfill(json=folders))
                page.route("**/api/problems/*/folder", update_folder)
                page.route(
                    "**/api/problems/*/samples**",
                    lambda route: route.fulfill(
                        json={
                            "profile": "sample",
                            "caseCount": 0,
                            "label": "visual",
                            "cases": [],
                        }
                    ),
                )
                route_empty_judge_secondary_data(page)
                page.goto(server.url)
                page.wait_for_function(
                    "() => document.querySelectorAll('#problemList [data-problem-id]').length === 41"
                )

                self.assertEqual(page.locator(".problem-folder-move-select").count(), 0)
                self.assertEqual(
                    page.locator("#problemList .problem-folder-move-action").count(),
                    1,
                )
                action_style = page.eval_on_selector(
                    "#problemList .problem-folder-move-action",
                    """element => ({
                        opacity: getComputedStyle(element).opacity,
                        pointerEvents: getComputedStyle(element).pointerEvents,
                    })""",
                )
                self.assertEqual(
                    action_style,
                    {"opacity": "1", "pointerEvents": "auto"},
                )

                page.reload()
                page.wait_for_function(
                    "() => document.querySelectorAll('#problemList [data-problem-id]').length === 41"
                )
                refreshed_action_style = page.eval_on_selector(
                    "#problemList .problem-folder-move-action",
                    """element => ({
                        opacity: getComputedStyle(element).opacity,
                        pointerEvents: getComputedStyle(element).pointerEvents,
                    })""",
                )
                self.assertEqual(
                    refreshed_action_style,
                    {"opacity": "1", "pointerEvents": "auto"},
                )
                overflowing = [
                    item
                    for item in element_overflow(page, "#problemList .list-item")
                    if item["scrollWidth"] > item["clientWidth"] + 1
                ]
                self.assertEqual(overflowing, [])

                action = page.locator('#problemList [data-folder-move-problem="mock-001"]')
                action.focus()
                geometry = page.evaluate(
                    """() => {
                        const action = document.querySelector(
                            '#problemList [data-folder-move-problem="mock-001"]'
                        );
                        const card = action.closest('.problem-item-row').querySelector('.list-item');
                        const a = action.getBoundingClientRect();
                        const c = card.getBoundingClientRect();
                        return {
                            overlap: Math.max(0, Math.min(a.right, c.right) - Math.max(a.left, c.left))
                                * Math.max(0, Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top)),
                        };
                    }"""
                )
                self.assertEqual(geometry["overlap"], 0)

                action.click()
                page.locator("#problemFolderMoveModal").wait_for(state="visible")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "problemFolderMoveSelect",
                )
                wait_for_text(page, "#problemFolderMoveProblemLabel", "mock-001")
                page.keyboard.press("Escape")
                page.locator("#problemFolderMoveModal").wait_for(state="hidden")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.dataset.folderMoveProblem"),
                    "mock-001",
                )

                action.click()
                page.locator("#problemFolderMoveSelect").select_option("Graph")
                page.locator("#problemFolderMoveConfirmButton").click()
                wait_for_text(page, "#toastHost", "mock-001 문제를 Graph 폴더로 옮겼습니다.")
                self.assertEqual(captured, {"problem_id": "mock-001", "folder": "Graph"})
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.dataset.folderMoveProblem"),
                    "mock-001",
                )

                page.evaluate(
                    """() => {
                        const source = document.querySelector('[data-problem-id="mock-003"]');
                        const target = document.querySelector(
                            '.problem-folder-group[data-folder="Graph"]'
                        );
                        const dataTransfer = new DataTransfer();
                        source.dispatchEvent(new DragEvent('dragstart', {
                            bubbles: true, cancelable: true, dataTransfer,
                        }));
                        target.dispatchEvent(new DragEvent('drop', {
                            bubbles: true, cancelable: true, dataTransfer,
                        }));
                        source.dispatchEvent(new DragEvent('dragend', {
                            bubbles: true, cancelable: true, dataTransfer,
                        }));
                    }"""
                )
                wait_for_text(page, "#toastHost", "mock-003 문제를 Graph 폴더로 옮겼습니다.")
                self.assertEqual(captured, {"problem_id": "mock-003", "folder": "Graph"})

    def test_100_problem_mobile_picker_keeps_touch_action_and_document_width(self) -> None:
        """100개 문제의 mobile picker action은 44px이며 공용 dialog를 사용합니다."""
        problems = [judge_problem(index, total=100) for index in range(1, 101)]
        with isolated_runtime("alj-plan53-judge-100-e2e-") as (_directory, runtime):
            with temporary_env(judge_env(runtime)), run_app(create_judge_app()) as server:
                page = self.new_page(server.url, width=390, height=844)
                folders = [
                    {"folder": "Graph", "label": "Graph", "problemCount": 50},
                    {"folder": "Math", "label": "Math", "problemCount": 50},
                ]
                page.route("**/api/problems", lambda route: route.fulfill(json=problems))
                page.route("**/api/folders", lambda route: route.fulfill(json=folders))
                page.route(
                    "**/api/problems/*/samples**",
                    lambda route: route.fulfill(
                        json={"profile": "sample", "caseCount": 0, "label": "visual", "cases": []}
                    ),
                )
                route_empty_judge_secondary_data(page)
                page.goto(server.url)
                page.locator("#problemJumpButton").wait_for(state="visible")
                page.locator("#problemJumpButton").click()
                page.wait_for_function(
                    "() => document.querySelectorAll('#problemPickerList [data-problem-id]').length === 100"
                )
                self.assertEqual(page.locator(".problem-folder-move-select").count(), 0)
                action = page.locator('#problemPickerList [data-folder-move-problem="mock-001"]')
                box = action.bounding_box()
                self.assertIsNotNone(box)
                self.assertGreaterEqual(box["width"], 44)
                self.assertGreaterEqual(box["height"], 44)
                width_metrics = page.evaluate(
                    """() => {
                        const root = document.documentElement;
                        const offenders = [...document.querySelectorAll('body *')]
                            .map((element) => {
                                const rect = element.getBoundingClientRect();
                                return {
                                    selector: element.id
                                        ? `#${element.id}`
                                        : `${element.tagName.toLowerCase()}.${element.className}`,
                                    left: rect.left,
                                    right: rect.right,
                                    width: rect.width,
                                    scrollWidth: element.scrollWidth,
                                    clientWidth: element.clientWidth,
                                };
                            })
                            .filter((item) => item.right > root.clientWidth + 1 || item.left < -1)
                            .slice(0, 12);
                        return {
                            scrollWidth: root.scrollWidth,
                            clientWidth: root.clientWidth,
                            offenders,
                        };
                    }"""
                )
                self.assertLessEqual(
                    width_metrics["scrollWidth"],
                    width_metrics["clientWidth"] + 1,
                    width_metrics,
                )
                action.click()
                page.locator("#problemFolderMoveModal").wait_for(state="visible")
                self.assertEqual(
                    page.locator("#problemFolderMoveModal").get_attribute("role"),
                    "dialog",
                )
                page.keyboard.press("Escape")
                page.locator("#problemFolderMoveModal").wait_for(state="hidden")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.dataset.folderMoveProblem"),
                    "mock-001",
                )


class Plan53StudioVisualRegressionE2ETest(BrowserE2ETestCase):
    """Studio Git drawer, repository actions, empty state와 목록 scroll을 검증합니다."""

    def test_git_drawer_handles_320_dirty_files_and_responsive_surfaces(self) -> None:
        """320개 변경에서도 Git 상태와 동작이 잘리지 않고 surface가 상호 배제됩니다."""
        with isolated_runtime("alj-plan53-studio-git-e2e-") as (_directory, workspace):
            git(workspace, "init")
            git(workspace, "config", "user.email", "studio@example.com")
            git(workspace, "config", "user.name", "Problem Studio")
            dirty_directory = workspace / "visual-dirty"
            dirty_directory.mkdir()
            for index in range(320):
                (dirty_directory / f"file-{index:03d}.txt").write_text(
                    "before\n", encoding="utf-8"
                )
            git(workspace, "add", "visual-dirty")
            git(workspace, "commit", "-m", "seed visual dirty files")
            for index in range(320):
                (dirty_directory / f"file-{index:03d}.txt").write_text("after\n", encoding="utf-8")

            with run_app(create_studio_app(workspace)) as server:
                page = self.new_page(server.url, width=1366, height=768)
                page.goto(server.url)
                page.locator("#gitDrawerButton").wait_for(state="visible")
                wait_for_text(page, "#gitDrawerButton", "변경 320")
                self.assertEqual(
                    page.evaluate(
                        """() => [...document.querySelectorAll('body *')].filter(
                            (element) => element.children.length === 0
                                && element.textContent.trim() === '첫 문제를 만들어 시작하세요'
                                && element.getClientRects().length
                        ).length"""
                    ),
                    1,
                )
                self.assertEqual(
                    page.evaluate(
                        """() => [...document.querySelectorAll('body *')].filter(
                            (element) => element.children.length === 0
                                && element.textContent.trim() === '아직 문제가 없습니다'
                                && element.getClientRects().length
                        ).length"""
                    ),
                    0,
                )

                repository_controls = element_overflow(
                    page,
                    "#repositoryCloneButton, #repositoryOpenButton, #repositoryRefreshButton",
                )
                self.assertTrue(repository_controls)
                self.assertTrue(
                    all(
                        item["scrollWidth"] <= item["clientWidth"] + 1
                        for item in repository_controls
                    ),
                    repository_controls,
                )
                refresh = page.locator("#repositoryRefreshButton")
                self.assertTrue(refresh.get_attribute("aria-label"))
                refresh_box = refresh.bounding_box()
                self.assertIsNotNone(refresh_box)
                self.assertGreaterEqual(refresh_box["width"], 44)
                self.assertGreaterEqual(refresh_box["height"], 44)

                page.locator("#gitDrawerButton").click()
                drawer = page.locator("#gitDrawer")
                drawer.wait_for(state="visible")
                self.assertEqual(drawer.get_attribute("role"), "complementary")
                self.assertIsNone(drawer.get_attribute("aria-modal"))
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "gitDrawerCloseButton",
                )
                wait_for_text(page, "#gitStatus", "변경 320개")
                status_metrics = page.locator("#gitStatus").evaluate(
                    """element => ({
                        clientHeight: element.clientHeight,
                        scrollHeight: element.scrollHeight,
                        overflowY: getComputedStyle(element).overflowY,
                    })"""
                )
                self.assertNotIn(status_metrics["overflowY"], {"auto", "scroll"})
                self.assertTrue(
                    status_metrics["clientHeight"] > 52
                    or status_metrics["scrollHeight"] <= status_metrics["clientHeight"] + 1,
                    status_metrics,
                )
                git_controls = element_overflow(
                    page,
                    "#gitFetchButton, #gitPullButton, #gitCommitButton, #gitPushButton",
                )
                self.assertTrue(
                    all(item["scrollWidth"] <= item["clientWidth"] + 1 for item in git_controls),
                    git_controls,
                )
                page.keyboard.press("Escape")
                drawer.wait_for(state="hidden")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "gitDrawerButton",
                )

                page.set_viewport_size({"width": 390, "height": 844})
                page.locator("#sidebarToggle").click()
                page.locator("#gitDrawerButton").click()
                drawer.wait_for(state="visible")
                self.assertEqual(drawer.get_attribute("role"), "dialog")
                self.assertEqual(drawer.get_attribute("aria-modal"), "true")
                self.assertFalse(
                    page.locator("body").evaluate(
                        "body => body.classList.contains('sidebar-open')"
                    )
                )
                self.assertTrue(page.locator(".shell").get_attribute("inert") is not None)

                page.evaluate("() => document.querySelector('#jobCenterButton').click()")
                page.locator("#jobCenterDrawer").wait_for(state="visible")
                drawer.wait_for(state="hidden")
                page.evaluate("() => document.querySelector('#gitDrawerButton').click()")
                drawer.wait_for(state="visible")
                page.locator("#jobCenterDrawer").wait_for(state="hidden")

                last_focusable = drawer.locator(
                    "button:not([disabled]), input:not([disabled]), select:not([disabled])"
                ).last
                last_focusable.focus()
                page.keyboard.press("Tab")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "gitDrawerCloseButton",
                )
                page.keyboard.press("Escape")
                drawer.wait_for(state="hidden")
                self.assertEqual(
                    page.evaluate("() => document.activeElement?.id"),
                    "sidebarToggle",
                )

    def test_100_problem_sidebar_keeps_only_problem_list_scrollable(self) -> None:
        """100개 문제에서도 sidebar 전체가 아니라 문제 목록만 독립 스크롤됩니다."""
        with isolated_runtime("alj-plan53-studio-100-e2e-") as (_directory, workspace):
            for index in range(100):
                create_problem(
                    workspace,
                    f"visual-{index:03d}",
                    f"Visual regression problem {index:03d}",
                )
            with run_app(create_studio_app(workspace)) as server:
                page = self.new_page(server.url, width=1440, height=900)
                page.goto(server.url)
                page.wait_for_function(
                    "() => document.querySelectorAll('#problemList [data-problem-id]').length === 100"
                )
                metrics = page.evaluate(
                    """() => {
                        const sidebar = document.querySelector('#studioSidebar');
                        const list = document.querySelector('#problemList');
                        const before = list.scrollTop;
                        list.scrollTop = 500;
                        return {
                            sidebarOverflowY: getComputedStyle(sidebar).overflowY,
                            sidebarScrollTop: sidebar.scrollTop,
                            listOverflowY: getComputedStyle(list).overflowY,
                            listClientHeight: list.clientHeight,
                            listScrollHeight: list.scrollHeight,
                            listBefore: before,
                            listAfter: list.scrollTop,
                            documentOverflow: document.documentElement.scrollWidth
                                - document.documentElement.clientWidth,
                        };
                    }"""
                )
                self.assertEqual(metrics["sidebarOverflowY"], "hidden")
                self.assertEqual(metrics["sidebarScrollTop"], 0)
                self.assertIn(metrics["listOverflowY"], {"auto", "scroll"})
                self.assertGreater(metrics["listScrollHeight"], metrics["listClientHeight"])
                self.assertGreater(metrics["listAfter"], metrics["listBefore"])
                self.assertLessEqual(metrics["documentOverflow"], 1)
                self.assert_no_browser_errors()
