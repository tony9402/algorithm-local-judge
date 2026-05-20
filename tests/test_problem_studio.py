from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from judge.core.cases_compile import CaseCompileResult, CompiledCase, CompiledProfile
from judge.core.errors import JudgeError
from problem_studio.core.bulk import build_all_problem_packs
from problem_studio.core.editor import safe_problem_file
from problem_studio.core.packflow import (
    SOLUTION_WARMUP_PROFILE,
    build_problem_pack,
    verify_solutions,
)
from problem_studio.web.app import create_app


class ProblemStudioTest(unittest.TestCase):
    """Smoke tests for the separated problem authoring web app."""

    def make_client(self) -> tuple[tempfile.TemporaryDirectory[str], TestClient, Path]:
        """Create a temporary authoring workspace and TestClient."""
        directory = tempfile.TemporaryDirectory(prefix="alj-problem-studio-")
        workspace = Path(directory.name)
        return directory, TestClient(create_app(workspace)), workspace

    def sse_events(self, text: str) -> list[tuple[str, dict]]:
        """Parse buffered Server-Sent Events from TestClient responses."""
        events = []
        for block in text.strip().split("\n\n"):
            if not block:
                continue
            event = "message"
            data_lines = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                if line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
            events.append((event, json.loads("\n".join(data_lines))))
        return events

    def test_static_ui_and_workspace_status(self) -> None:
        """The studio app should serve its UI and workspace summary."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)

        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers.get("cache-control"), "no-store")
        self.assertIn("Problem Studio", page.text)
        self.assertIn("newProblemButton", page.text)
        self.assertIn("workspaceBuildAllButton", page.text)
        self.assertIn("workspaceBuildModal", page.text)
        self.assertIn("bulkProblemList", page.text)
        self.assertIn("workspaceBuildStartButton", page.text)
        self.assertIn("metadataFolder", page.text)
        self.assertIn("metadataProblemIdInput", page.text)
        self.assertIn("metadataCompileTimeout", page.text)
        self.assertIn("metadataToolGenerator", page.text)
        self.assertIn("metadataToolSolution", page.text)
        self.assertIn("metadata-id-chip", page.text)
        self.assertIn("metadataValidationSummary", page.text)
        self.assertIn("newProblemFolder", page.text)
        self.assertIn("newProblemDefaultProfile", page.text)
        self.assertIn("newProblemUserTimeout", page.text)
        self.assertIn("deleteProblemModal", page.text)
        self.assertIn("deleteProblemConfirmInput", page.text)
        self.assertIn("문제 정보", page.text)
        self.assertIn("데이터 생성", page.text)
        self.assertIn("데이터 벨리데이션", page.text)
        self.assertIn("채점기", page.text)
        self.assertIn("솔루션", page.text)
        self.assertIn("loadingOverlay", page.text)
        self.assertIn("loading-title-row", page.text)
        self.assertIn("progressPanel", page.text)
        self.assertIn("progressSteps", page.text)
        self.assertIn("progressSummary", page.text)
        self.assertIn("progressInsight", page.text)
        self.assertIn("lastRunPanel", page.text)
        self.assertIn("studio-tabs", page.text)
        self.assertIn("tab-marker", page.text)
        self.assertIn("tab-hint", page.text)
        self.assertIn("입력 조건 검증", page.text)
        self.assertIn("globalTaskStatus", page.text)
        self.assertIn("alertStack", page.text)
        self.assertIn("문제 패널 닫기", page.text)
        self.assertIn("워크스페이스", page.text)
        self.assertIn("저장", page.text)
        self.assertIn("문제 만들기", page.text)
        self.assertIn("문제 삭제", page.text)
        self.assertIn("솔루션 이름", page.text)
        self.assertIn("codeHighlight", page.text)
        self.assertIn("sidebarToggle", page.text)
        self.assertIn("mobileHeaderTitle", page.text)
        self.assertIn("mobileHeaderMeta", page.text)
        self.assertIn("sidebar-toggle-icon", page.text)
        self.assertIn("solutionCreateModal", page.text)
        self.assertIn("solutionEditModal", page.text)
        self.assertIn("solutionCasesModal", page.text)
        self.assertIn("solution-editor-modal", page.text)
        self.assertIn("solution-editor-source", page.text)
        self.assertIn("source-section-label", page.text)
        self.assertIn("source-modal-editor", page.text)
        self.assertIn("modal-editor-toolbar", page.text)
        self.assertIn("solutionValidationSummary", page.text)
        self.assertIn("resourceSummary", page.text)
        self.assertIn("resourceFilterInput", page.text)
        self.assertIn("last-run-kicker", page.text)
        self.assertIn("editorSettingsButton", page.text)
        self.assertIn("editorSettingsPanel", page.text)
        self.assertIn("editorModeVim", page.text)
        self.assertIn("editorModeBadge", page.text)
        self.assertIn("editorStatusBar", page.text)
        self.assertIn("editorCommandLine", page.text)
        self.assertIn("파일 편집기", page.text)
        self.assertIn("buildPanel", page.text)
        self.assertIn("buildDashboard", page.text)
        self.assertIn("packDownloadLink", page.text)
        self.assertIn("buildDashboardDownloadLink", page.text)
        self.assertIn("검증/빌드", page.text)
        self.assertIn("솔루션 편집", page.text)
        self.assertIn("솔루션 파일 생성", page.text)
        self.assertIn("codemirror.min.js", page.text)
        self.assertIn("keymap/vim.min.js", page.text)
        self.assertIn('type="module" src="/static/app.js', page.text)
        self.assertNotIn("Link testlib.h", page.text)
        self.assertNotIn("Diagnostics", page.text)
        self.assertNotIn("diagnosticsBoard", page.text)
        self.assertNotIn("resultSummary", page.text)
        self.assertNotIn("result-panel", page.text)
        self.assertNotIn("Raw log", page.text)
        self.assertNotIn("최근 이벤트", page.text)
        self.assertNotIn("전체 로그 보기", page.text)
        self.assertNotIn(">Save<", page.text)
        self.assertNotIn(">Create<", page.text)
        self.assertNotIn(">Problems<", page.text)

        script = client.get("/static/app.js")
        self.assertEqual(script.status_code, 200)
        state_module = client.get("/static/app/state.js")
        self.assertEqual(state_module.status_code, 200)
        api_module = client.get("/static/app/api.js")
        self.assertEqual(api_module.status_code, 200)
        sse_module = client.get("/static/app/sse.js")
        self.assertEqual(sse_module.status_code, 200)
        dom_module = client.get("/static/app/dom.js")
        self.assertEqual(dom_module.status_code, 200)
        storage_module = client.get("/static/app/storage.js")
        self.assertEqual(storage_module.status_code, 200)
        self.assertIn("export const state", state_module.text)
        self.assertIn("export async function api", api_module.text)
        self.assertIn("export function streamProgressDetail", sse_module.text)
        self.assertIn("export const optional", dom_module.text)
        self.assertIn("export function readStorage", storage_module.text)
        self.assertIn("function bindEvents", script.text)
        self.assertIn("function withLoading", script.text)
        self.assertIn("function showAlert", script.text)
        self.assertIn("function normalizeErrorDetail", api_module.text)
        self.assertIn("function confirmDiscardChanges", script.text)
        self.assertIn("function beginProgress", script.text)
        self.assertIn("function setProgressStep", script.text)
        self.assertIn("function setProgressInsight", script.text)
        self.assertIn("function streamProgressDetail", sse_module.text)
        self.assertIn("function validateAllData", script.text)
        self.assertIn("모든 데이터 생성+검증", script.text)
        self.assertIn("function showLastRun", script.text)
        self.assertIn("function restoreProblemLastResult", script.text)
        self.assertIn("function storedLastResults", script.text)
        self.assertIn("function applyProblemMetadataToUi", script.text)
        self.assertIn("function updateMetadataPreview", script.text)
        self.assertIn("function positiveIntegerInput", script.text)
        self.assertIn("function metadataFormIssues", script.text)
        self.assertIn("function applyProblemRenameResult", script.text)
        self.assertIn("SAFE_PROBLEM_ID", state_module.text)
        self.assertIn("function renderMetadataValidation", script.text)
        self.assertIn("function metadataRawEditorDirty", script.text)
        self.assertIn("metadataToolGeneratorConfig", script.text)
        self.assertIn("metadataSolutionTimeout", script.text)
        self.assertIn("newProblemDefaultProfile", script.text)
        self.assertIn("function openDeleteProblemModal", script.text)
        self.assertIn("function deleteSelectedProblem", script.text)
        self.assertIn("DELETE_CONFIRM_PHRASE", script.text)
        self.assertIn("function folderLabel", script.text)
        self.assertIn("function toggleProblemFolder", script.text)
        self.assertIn("problemFolderCollapsed", state_module.text)
        self.assertIn("function updateBuildPanel", script.text)
        self.assertIn("function updateBuildDashboard", script.text)
        self.assertIn("function validationStatusForFile", script.text)
        self.assertIn("function errorKindForDetail", script.text)
        self.assertIn("function formatOperationFailure", script.text)
        self.assertIn("오류 유형", script.text)
        self.assertIn("Generator 런타임 오류", script.text)
        self.assertIn("resourceFilters", script.text)
        self.assertIn("function hasFreshFullTest", script.text)
        self.assertIn("PACK_OUTPUT_DIR", script.text)
        self.assertIn("function formatSolutionFailureSummary", script.text)
        self.assertIn("function failedSolutionChecks", script.text)
        self.assertIn("solutionCheckSource", script.text)
        self.assertIn("function renderSolutionValidationSummary", script.text)
        self.assertIn("function solutionValidationStatusForFile", script.text)
        self.assertIn("function solutionCheckDetailRows", script.text)
        self.assertIn("function openSolutionCasesModal", script.text)
        self.assertIn("function renderSolutionCasesBody", script.text)
        self.assertIn("function renderSolutionFailureItem", script.text)
        self.assertIn("lastSolutionVerification", script.text)
        self.assertIn("beforeunload", script.text)
        self.assertIn("aria-selected", script.text)
        self.assertIn("function createSolution", script.text)
        self.assertIn("function renameSolution", script.text)
        self.assertIn("function openSolutionEditModal", script.text)
        self.assertIn("function verifySingleSolution", script.text)
        self.assertIn('action.id === "uploadSolutions"', script.text)
        self.assertIn("encodeURIComponent(state.selectedProblem)", script.text)
        self.assertIn("function mergeSolutionVerification", script.text)
        self.assertIn("function highlightCode", script.text)
        self.assertIn("function initializeCodeMirror", script.text)
        self.assertIn("function initializeSourceModalEditors", script.text)
        self.assertIn("function modalEditorKeyForElement", script.text)
        self.assertIn("function focusModalEditor", script.text)
        self.assertIn("function syncModalEditorMode", script.text)
        self.assertIn("function modalEditorLanguage", script.text)
        self.assertIn("function getEditorValue", script.text)
        self.assertIn("function getModalEditorValue", script.text)
        self.assertIn("function forceHideLoading", script.text)
        self.assertIn("function handleCodeMirrorBeforeChange", script.text)
        self.assertIn("function handleCodeMirrorBeforeInput", script.text)
        self.assertIn("function handleEditorKeydown", script.text)
        self.assertIn("function handleVimKeydown", script.text)
        self.assertIn("function setEditorMode", script.text)
        self.assertIn("function updateEditorStatus", script.text)
        self.assertIn("function ensureEditorCursorVisible", script.text)
        self.assertIn("function enterVimVisualMode", script.text)
        self.assertIn("function handleVimVisualKey", script.text)
        self.assertIn("function vimCountValue", script.text)
        self.assertIn("function findVimSearch", script.text)
        self.assertIn("function undoEditorChange", script.text)
        self.assertIn("function currentPrimaryAction", script.text)
        self.assertIn("editorCommandInput", script.text)
        self.assertIn("function restoreEditorSettings", script.text)
        self.assertIn('const EDITOR_INDENT = "    "', state_module.text)
        self.assertIn("EDITOR_SETTINGS_KEY", state_module.text)
        self.assertIn("PERSISTED_VIEW_KEY", state_module.text)
        self.assertIn("function restoreViewPreference", script.text)
        self.assertIn("function runAllChecksOnce", script.text)
        self.assertIn("function withProblemTaskLock", script.text)
        self.assertIn("function shouldDisplayLastRunPanel", script.text)
        self.assertIn("function renderLastRunPanel", script.text)
        self.assertIn("navigator.locks", script.text)
        self.assertIn("PACK_JOB_KEY", state_module.text)
        self.assertIn("LAST_RESULTS_KEY", state_module.text)
        self.assertIn("PROBLEM_TASK_LOCK_NAME", state_module.text)
        self.assertIn("function startPackBuild", script.text)
        self.assertIn("function startPackBuildOnce", script.text)
        self.assertIn("function buildPack", script.text)
        self.assertIn("function buildAllPacks", script.text)
        self.assertIn("function buildAllPacksOnce", script.text)
        self.assertIn("function openWorkspaceBuildModal", script.text)
        self.assertIn("function selectedBulkProblemIdsFromModal", script.text)
        self.assertIn("workspaceBuildAllButton", script.text)
        self.assertIn("function bulkBuildButtons", script.text)
        self.assertIn("manualProgress", script.text)
        self.assertIn("워커로 병렬 실행 중", sse_module.text)
        self.assertIn("/api/workspace/packs/build-all/stream", script.text)
        self.assertIn("전체 문제 테스트/팩 빌드", script.text)
        self.assertNotIn("문제 번호 순서를 확인하세요", script.text)
        self.assertIn("팩 빌드 전에 전체 테스트를 자동으로 실행합니다.", script.text)
        self.assertIn("전체 테스트를 통과하지 못해 팩 빌드를 중단했습니다.", script.text)
        self.assertIn("function pollPackJob", script.text)
        self.assertIn("function saveOpenFileIfDirty", script.text)
        self.assertIn("function roleForFile", script.text)
        self.assertIn("function runTabAction", script.text)
        self.assertIn("resource-role", script.text)
        self.assertIn("function solutionCheckMetrics", script.text)
        self.assertIn("function renderSolutionCaseRows", script.text)
        self.assertIn("function selectSolutionPath", script.text)
        self.assertIn("solutions-mode", script.text)
        self.assertIn("maintainedCount", script.text)
        self.assertIn('panel.className = "solution-validation-summary hidden";', script.text)
        self.assertNotIn("Skipped ", script.text)
        self.assertNotIn("resultSummary", script.text)
        self.assertNotIn("resultOutput", script.text)
        self.assertNotIn("diagnosticsBoard", script.text)

        stylesheet = client.get("/static/styles.css")
        self.assertEqual(stylesheet.status_code, 200)
        codemirror = client.get("/static/vendor/codemirror/codemirror.min.js")
        self.assertEqual(codemirror.status_code, 200)
        self.assertIn("CodeMirror", codemirror.text)
        self.assertIn("body.sidebar-open .sidebar", stylesheet.text)
        self.assertIn(".mobile-header-copy", stylesheet.text)
        self.assertIn(".mobile-header-meta", stylesheet.text)
        self.assertIn(".tab-marker", stylesheet.text)
        self.assertIn(".tab-hint", stylesheet.text)
        self.assertIn(".editor-settings-panel", stylesheet.text)
        self.assertIn(".segmented-control", stylesheet.text)
        self.assertIn(".editor-mode-badge", stylesheet.text)
        self.assertIn(".editor-status-bar", stylesheet.text)
        self.assertIn(".editor-command-line", stylesheet.text)
        self.assertIn("white-space: pre-wrap", stylesheet.text)
        self.assertIn("width: min(720px", stylesheet.text)
        self.assertIn("body.sidebar-open .sidebar-toggle-icon", stylesheet.text)
        self.assertIn("transform: translateX(-102%)", stylesheet.text)
        self.assertIn(".app-alert", stylesheet.text)
        self.assertIn(".problem-folder", stylesheet.text)
        self.assertIn(".problem-folder-section", stylesheet.text)
        self.assertIn(".metadata-card", stylesheet.text)
        self.assertIn(".metadata-limit-grid", stylesheet.text)
        self.assertIn(".number-with-unit", stylesheet.text)
        self.assertIn(".metadata-details", stylesheet.text)
        self.assertIn(".metadata-validation-summary", stylesheet.text)
        self.assertIn(".studio-layout.info-mode", stylesheet.text)
        self.assertIn(".danger-note", stylesheet.text)
        self.assertIn("button.danger", stylesheet.text)
        self.assertIn(".field-error", stylesheet.text)
        self.assertIn(".global-task-status", stylesheet.text)
        self.assertIn(".resource-role", stylesheet.text)
        self.assertIn(".solution-validation-summary", stylesheet.text)
        self.assertIn(".solution-row-main", stylesheet.text)
        self.assertIn(".solution-metric-strip", stylesheet.text)
        self.assertIn(".studio-layout.solutions-mode .action-grid", stylesheet.text)
        self.assertIn("max-width: none", stylesheet.text)
        self.assertIn("clip-path: inset(50%)", stylesheet.text)
        self.assertIn(".solution-case-table", stylesheet.text)
        self.assertIn(".solution-case-row", stylesheet.text)
        self.assertIn(".solution-cases-modal", stylesheet.text)
        self.assertIn(".solution-cases-summary", stylesheet.text)
        self.assertIn(".solution-editor-modal", stylesheet.text)
        self.assertIn(".source-modal-editor", stylesheet.text)
        self.assertIn(".modal-editor-toolbar", stylesheet.text)
        self.assertIn(".source-modal-codemirror", stylesheet.text)
        self.assertIn(".studio-codemirror", stylesheet.text)
        self.assertIn(".studio-codemirror .cm-meta", stylesheet.text)
        self.assertIn(".studio-codemirror .cm-def", stylesheet.text)
        self.assertIn(".solution-validation-detail-row", stylesheet.text)
        self.assertIn(".solution-validation-failure", stylesheet.text)
        self.assertIn(".resource-item.mismatch", stylesheet.text)
        self.assertIn(".resource-item.match", stylesheet.text)
        self.assertIn(".resource-item.match.active", stylesheet.text)
        self.assertIn(".resource-item.mismatch.active", stylesheet.text)
        self.assertIn(".progress-steps", stylesheet.text)
        self.assertIn(".progress-insight", stylesheet.text)
        self.assertIn(".progress-summary", stylesheet.text)
        self.assertIn(".last-run-panel", stylesheet.text)
        self.assertNotIn(".result-panel", stylesheet.text)
        self.assertNotIn(".progress-log", stylesheet.text)
        self.assertNotIn(".debug-log", stylesheet.text)

        status = client.get("/api/workspace")
        self.assertEqual(status.status_code, 200, status.text)
        data = status.json()
        self.assertEqual(Path(data["workspace"]), workspace.resolve())
        self.assertEqual(data["problemCount"], 0)
        self.assertEqual(data["problems"], [])
        self.assertEqual(data["folders"], [])

    def test_create_edit_compile_and_list_solutions(self) -> None:
        """A new problem should be editable and cases.yml should compile."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)

        created = client.post(
            "/api/problems",
            json={
                "problem_id": "alpha",
                "title": "Echo Number",
                "folder": "Basics",
                "version": 3,
                "default_profile": "full",
                "limits": {
                    "compileTimeoutMs": 7000,
                    "generationTimeoutMs": 8000,
                    "solutionTimeoutMs": 3000,
                    "userTimeoutMs": 2500,
                },
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["metadata"]["problemId"], "alpha")
        self.assertEqual(created.json()["metadata"]["folder"], "Basics")
        self.assertEqual(created.json()["metadata"]["version"], 3)
        self.assertEqual(created.json()["metadata"]["defaultProfile"], "full")
        self.assertEqual(created.json()["metadata"]["limits"]["userTimeoutMs"], 2500)

        problems = client.get("/api/problems")
        self.assertEqual(problems.status_code, 200, problems.text)
        self.assertEqual(problems.json()[0]["problemId"], "alpha")
        self.assertEqual(problems.json()[0]["folder"], "Basics")

        files = client.get("/api/problems/alpha/files")
        self.assertEqual(files.status_code, 200, files.text)
        paths = {item["path"] for item in files.json()["files"]}
        self.assertIn("problem.json", paths)
        self.assertIn("generator/cases.yml", paths)
        self.assertIn("solutions/main_solution.ac.cpp", paths)

        cases = client.get("/api/problems/alpha/files/generator/cases.yml")
        self.assertEqual(cases.status_code, 200, cases.text)
        self.assertIn("matrix:", cases.json()["content"])

        written = client.put(
            "/api/problems/alpha/files/notes.md",
            json={"content": "author notes\n"},
        )
        self.assertEqual(written.status_code, 200, written.text)
        note = client.get("/api/problems/alpha/files/notes.md")
        self.assertEqual(note.status_code, 200, note.text)
        self.assertEqual(note.json()["content"], "author notes\n")

        compiled = client.post("/api/problems/alpha/cases/compile", json={"profile": "hidden"})
        self.assertEqual(compiled.status_code, 200, compiled.text)
        self.assertTrue(compiled.json()["valid"], compiled.text)
        self.assertEqual(compiled.json()["profiles"][0]["caseCount"], 5)

        solutions = client.get("/api/problems/alpha/solutions")
        self.assertEqual(solutions.status_code, 200, solutions.text)
        self.assertEqual(solutions.json()["solutions"][0]["expectedStatus"], "accepted")

        upload = client.post(
            "/api/problems/alpha/solutions/upload",
            files=[
                ("files", ("wrong_solution.wa.py", b"print(0)\n", "text/x-python")),
                ("files", ("slow_solution.tle.java", b"class Main {}\n", "text/x-java")),
            ],
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        uploaded_paths = {item["path"] for item in upload.json()["uploaded"]}
        self.assertEqual(
            uploaded_paths,
            {"solutions/wrong_solution.wa.py", "solutions/slow_solution.tle.java"},
        )
        solution_statuses = {
            item["path"]: item["expectedStatus"] for item in upload.json()["solutions"]
        }
        self.assertEqual(solution_statuses["solutions/wrong_solution.wa.py"], "wrong_answer")
        self.assertEqual(solution_statuses["solutions/slow_solution.tle.java"], "time_limit")

        created_solution = client.post(
            "/api/problems/alpha/solutions/create",
            json={"name": "memory_solution", "expected": "mle", "language": "cpp"},
        )
        self.assertEqual(created_solution.status_code, 200, created_solution.text)
        self.assertEqual(
            created_solution.json()["created"]["path"],
            "solutions/memory_solution.mle.cpp",
        )
        created_file = client.get("/api/problems/alpha/files/solutions/memory_solution.mle.cpp")
        self.assertEqual(created_file.status_code, 200, created_file.text)
        self.assertIn("int main", created_file.json()["content"])

        renamed_solution = client.patch(
            "/api/problems/alpha/solutions/rename",
            json={
                "path": "solutions/memory_solution.mle.cpp",
                "name": "renamed_solution",
                "expected": "wa",
                "language": "python",
            },
        )
        self.assertEqual(renamed_solution.status_code, 200, renamed_solution.text)
        self.assertEqual(
            renamed_solution.json()["renamed"]["path"],
            "solutions/renamed_solution.wa.py",
        )
        renamed_file = client.get("/api/problems/alpha/files/solutions/renamed_solution.wa.py")
        self.assertEqual(renamed_file.status_code, 200, renamed_file.text)

        renamed_reference = client.patch(
            "/api/problems/alpha/solutions/rename",
            json={
                "path": "solutions/main_solution.ac.cpp",
                "name": "reference",
                "expected": "ac",
                "language": "cpp",
            },
        )
        self.assertEqual(renamed_reference.status_code, 200, renamed_reference.text)
        self.assertEqual(
            renamed_reference.json()["metadata"]["tools"]["solution"],
            "solutions/reference.ac.cpp",
        )

        with patch(
            "problem_studio.web.routes.solutions.verify_solutions",
            return_value={
                "problemId": "01",
                "profile": "hidden",
                "passed": True,
                "verifiedCount": 1,
                "totalCount": 1,
                "skippedCount": 0,
                "checks": [],
            },
        ) as mocked_verify:
            response = client.post(
                "/api/problems/alpha/solutions/verify/stream",
                json={"profile": "hidden", "solutions": ["solutions/reference.ac.cpp"]},
            )

        self.assertEqual(response.status_code, 200, response.text)
        events = self.sse_events(response.text)
        result = next(data for event, data in events if event == "result")
        self.assertEqual(result["verifiedCount"], 1)
        self.assertEqual(
            mocked_verify.call_args.kwargs["solutions"],
            ["solutions/reference.ac.cpp"],
        )

    def test_problem_delete_requires_exact_confirmation(self) -> None:
        """Deleting a problem should require the exact Korean confirmation phrase."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)

        created = client.post(
            "/api/problems",
            json={"problem_id": "string-id", "title": "Foldered", "folder": "Graphs"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertTrue((workspace / "problems" / "string-id").exists())

        status = client.get("/api/workspace")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(
            status.json()["folders"],
            [{"name": "Graphs", "label": "Graphs", "problemCount": 1}],
        )

        rejected = client.request(
            "DELETE",
            "/api/problems/string-id",
            json={"confirm_phrase": "확인"},
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertTrue((workspace / "problems" / "string-id").exists())

        deleted = client.request(
            "DELETE",
            "/api/problems/string-id",
            json={"confirm_phrase": "확인했습니다"},
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertTrue(deleted.json()["deleted"])
        self.assertFalse((workspace / "problems" / "string-id").exists())
        self.assertEqual(deleted.json()["workspace"]["problemCount"], 0)

    def test_testlib_link_and_path_safety(self) -> None:
        """The workspace helper should expose testlib.h without allowing traversal."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "01", "title": "Safety"})

        linked = client.post("/api/workspace/testlib-link")
        self.assertEqual(linked.status_code, 200, linked.text)
        self.assertTrue((workspace / "problems" / "testlib.h").is_symlink())
        self.assertTrue(linked.json()["workspaceExists"])

        with self.assertRaisesRegex(JudgeError, "invalid problem file path"):
            safe_problem_file(workspace, "01", "../escaped.txt")

    def test_build_pack_uses_workspace_pack_output_dir(self) -> None:
        """The web pack flow should write artifacts below the workspace output folder."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-") as tmp:
            workspace = Path(tmp)
            (workspace / "problems" / "01").mkdir(parents=True)
            archive_path = workspace / "dist" / "packs" / "pack.tar.gz"
            fake_result = SimpleNamespace(
                archive_path=archive_path,
                pack_id="pack",
                platform_id="linux-amd64",
                problems=["01"],
                solution_checks={"passed": True},
            )

            with patch(
                "problem_studio.core.packflow.build_pack",
                return_value=fake_result,
            ) as mocked:
                result = build_problem_pack(workspace, "01", "pack", Path("dist/packs"))

            self.assertEqual(result["archiveLabel"], "dist/packs/pack.tar.gz")
            self.assertEqual(mocked.call_args.args[3], workspace / "dist" / "packs")
            self.assertEqual(
                mocked.call_args.kwargs["warmup_profile"],
                SOLUTION_WARMUP_PROFILE,
            )

    def test_verify_solutions_uses_sample_warmup(self) -> None:
        """Problem Studio solution checks should warm submissions with sample data."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-") as tmp:
            workspace = Path(tmp)
            fake_result = SimpleNamespace(to_dict=lambda root: {"root": str(root)})

            with patch(
                "problem_studio.core.packflow.verify_problem_solutions",
                return_value=fake_result,
            ) as mocked:
                result = verify_solutions(workspace, "01", "hidden")

            self.assertEqual(result["root"], str(workspace))
            self.assertEqual(
                mocked.call_args.kwargs["warmup_profile"],
                SOLUTION_WARMUP_PROFILE,
            )

    def test_validate_stream_generates_every_profile(self) -> None:
        """The validator tab should be able to force-generate and validate all profiles."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "01", "title": "Validation"})

        sample_dir = workspace / ".judge-cache" / "sample"
        hidden_dir = workspace / ".judge-cache" / "hidden"
        sample_dir.mkdir(parents=True)
        hidden_dir.mkdir(parents=True)
        (sample_dir / "manifest.json").write_text(
            json.dumps({"profile": "sample", "cases": [{"name": "s1"}]}),
            encoding="utf-8",
        )
        (hidden_dir / "manifest.json").write_text(
            json.dumps({"profile": "hidden", "cases": [{"name": "h1"}, {"name": "h2"}]}),
            encoding="utf-8",
        )
        compile_result = CaseCompileResult(
            path=workspace / "problems" / "01" / "generator" / "cases.yml",
            profiles=[
                CompiledProfile("sample", [CompiledCase(1, "s1", "fixed")]),
                CompiledProfile(
                    "hidden",
                    [CompiledCase(1, "h1", "generator"), CompiledCase(2, "h2", "generator")],
                ),
            ],
        )
        case_counts = {"sample": 1, "hidden": 2}
        data_dirs = {"sample": sample_dir, "hidden": hidden_dir}

        def fake_generate(problem_id, profile, force=False, root=None, progress=None):
            for index in range(1, case_counts[profile] + 1):
                if progress is not None:
                    progress(
                        f"Validating generated case {profile}_{index} "
                        f"({index}/{case_counts[profile]})."
                    )
            return data_dirs[profile]

        with (
            patch(
                "problem_studio.core.validation.compile_problem_cases",
                return_value=compile_result,
            ) as mocked_compile,
            patch(
                "problem_studio.core.validation.generate",
                side_effect=fake_generate,
            ) as mocked_generate,
        ):
            response = client.post("/api/problems/01/validate/stream", json={"force": True})

        self.assertEqual(response.status_code, 200, response.text)
        events = self.sse_events(response.text)
        logs = [data["message"] for event, data in events if event == "log"]
        result = next(data for event, data in events if event == "result")
        self.assertEqual(mocked_compile.call_args.args, ("01", None, workspace.resolve()))
        self.assertEqual(
            [call.args[:2] for call in mocked_generate.call_args_list],
            [("01", "sample"), ("01", "hidden")],
        )
        self.assertTrue(all(call.kwargs["force"] for call in mocked_generate.call_args_list))
        self.assertIn("Generating and validating profile sample (1/2).", logs)
        self.assertIn("sample: 1/3 data generated and validated.", logs)
        self.assertIn("hidden: 3/3 data generated and validated.", logs)
        self.assertEqual(result["profileCount"], 2)
        self.assertEqual(result["caseCount"], 3)
        self.assertEqual([profile["name"] for profile in result["profiles"]], ["sample", "hidden"])

    def test_pack_build_can_run_as_background_job(self) -> None:
        """The web API should start pack builds as pollable background jobs."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "01", "title": "Pack"})
        fake_result = {
            "archivePath": str(workspace / "dist" / "packs" / "basic.aljpack"),
            "archiveLabel": "dist/packs/basic.aljpack",
            "packId": "basic",
            "platformId": "linux-amd64",
            "problems": ["01"],
            "solutionChecks": {"passed": True},
        }

        with patch(
            "problem_studio.web.routes.packs.build_problem_pack",
            return_value=fake_result,
        ) as mocked:
            started = client.post(
                "/api/problems/01/packs/build",
                json={"pack_id": "basic", "verify_profile": "hidden"},
            )
            self.assertEqual(started.status_code, 200, started.text)
            job = started.json()
            self.assertEqual(job["kind"], "pack-build")
            self.assertEqual(job["problemId"], "01")

            status = job
            for _ in range(50):
                polled = client.get(f"/api/problems/01/packs/jobs/{job['jobId']}")
                self.assertEqual(polled.status_code, 200, polled.text)
                status = polled.json()
                if status["status"] != "running":
                    break
                time.sleep(0.01)

            self.assertEqual(status["status"], "succeeded")
            self.assertEqual(status["result"]["archiveLabel"], "dist/packs/basic.aljpack")
            self.assertEqual(
                status["result"]["downloadUrl"],
                f"/api/problems/01/packs/jobs/{job['jobId']}/download",
            )
            self.assertEqual(mocked.call_args.args[1], "01")
            self.assertEqual(mocked.call_args.args[3], Path("dist/packs"))

            archive = workspace / "dist" / "packs" / "basic.aljpack"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"pack")
            download = client.get(f"/api/problems/01/packs/jobs/{job['jobId']}/download")
            self.assertEqual(download.status_code, 200, download.text)
            self.assertEqual(download.content, b"pack")

    def test_workspace_can_stream_bulk_pack_build(self) -> None:
        """The web API should stream an all-problem test and pack build."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        fake_result = {
            "passed": True,
            "problemCount": 2,
            "packCount": 1,
            "packId": "basic",
            "outputDir": "dist/packs",
            "summary": "2개 문제 테스트 통과 · 1개 팩 생성",
            "pack": {
                "archiveLabel": "dist/packs/basic.aljpack",
                "problems": ["01", "02"],
            },
            "problems": [
                {
                    "problemId": "01",
                    "passed": True,
                    "summary": "ok",
                    "pack": {"archiveLabel": "dist/packs/basic.aljpack"},
                },
                {
                    "problemId": "02",
                    "passed": True,
                    "summary": "ok",
                    "pack": {"archiveLabel": "dist/packs/basic.aljpack"},
                },
            ],
            "packs": [{"archiveLabel": "dist/packs/basic.aljpack"}],
            "failedCount": 0,
        }

        with patch(
            "problem_studio.web.routes.bulk.build_all_problem_packs",
            return_value=fake_result,
        ) as mocked:
            response = client.post(
                "/api/workspace/packs/build-all/stream",
                json={
                    "pack_id": "basic",
                    "verify_profile": "hidden",
                    "force": True,
                    "problem_ids": ["01", "02"],
                    "max_workers": 2,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        events = self.sse_events(response.text)
        logs = [data["message"] for event, data in events if event == "log"]
        result = next(data for event, data in events if event == "result")
        self.assertIn("Starting full workspace test and pack build.", logs)
        self.assertIn(fake_result["summary"], logs)
        self.assertTrue(result["passed"])
        self.assertEqual(result["packCount"], 1)
        self.assertEqual(mocked.call_args.args[0], workspace.resolve())
        self.assertEqual(mocked.call_args.args[1:3], ("basic", Path("dist/packs")))
        self.assertEqual(mocked.call_args.args[4], "hidden")
        self.assertTrue(mocked.call_args.args[5])
        self.assertEqual(mocked.call_args.args[7], 2)
        self.assertEqual(mocked.call_args.args[8], ["01", "02"])

    def test_bulk_pack_build_runs_problems_in_parallel(self) -> None:
        """The all-problem builder should run independent problems concurrently."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-") as tmp:
            workspace = Path(tmp)
            first_started = threading.Event()
            second_started = threading.Event()

            def fake_full_test(*args, **kwargs) -> dict:
                problem_id = args[1]
                if problem_id == "01":
                    first_started.set()
                    if not second_started.wait(2):
                        raise RuntimeError("second problem did not start in parallel")
                if problem_id == "02":
                    second_started.set()
                    if not first_started.wait(2):
                        raise RuntimeError("first problem did not start in parallel")
                return {
                    "problemId": problem_id,
                    "passed": True,
                    "summary": "ok",
                    "solutionVerification": {"checks": []},
                }

            def fake_pack(*args, **kwargs) -> dict:
                problem_ids = args[1]
                return {
                    "archiveLabel": "dist/packs/basic.aljpack",
                    "problems": problem_ids,
                }

            with (
                patch("problem_studio.core.bulk.discover_problem_ids", return_value=["01", "02"]),
                patch(
                    "problem_studio.core.bulk.run_problem_full_test",
                    side_effect=fake_full_test,
                ),
                patch("problem_studio.core.bulk.build_problem_pack_bundle", side_effect=fake_pack),
            ):
                result = build_all_problem_packs(
                    workspace,
                    "basic",
                    Path("dist/packs"),
                    max_workers=2,
                )

        self.assertTrue(result["passed"])
        self.assertEqual(result["parallelWorkers"], 2)
        self.assertEqual([item["problemId"] for item in result["problems"]], ["01", "02"])
        self.assertEqual(result["packCount"], 1)
        self.assertEqual(result["packs"][0]["problems"], ["01", "02"])


if __name__ == "__main__":
    unittest.main()
