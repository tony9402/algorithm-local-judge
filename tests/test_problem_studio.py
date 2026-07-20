"""문제 스튜디오 API와 백그라운드 작업 저장소의 작업 흐름, 보안 정책, 일괄 빌드 계약을 검증하는 테스트 모듈입니다."""

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

from alj_core.cases_compile import CaseCompileResult, CompiledCase, CompiledProfile
from alj_core.errors import JudgeError
from alj_core.solution_models import SolutionCheckResult
from problem_studio.core.bulk import build_all_problem_packs
from problem_studio.core.editor import safe_problem_file
from problem_studio.core.packflow import (
    SOLUTION_WARMUP_PROFILE,
    build_problem_pack,
    verify_solutions,
)
from problem_studio.core.templates import create_problem
from problem_studio.web.app import create_app
from problem_studio.web.jobs import BackgroundJobStore, CancelToken, JobCancelledError
from problem_studio.web.routes.bulk import WORKSPACE_JOB_PROBLEM_ID
from problem_studio.web.routes.common import enqueue_background_job


class ProblemStudioTest(unittest.TestCase):
    """문제 스튜디오 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def make_client(self) -> tuple[tempfile.TemporaryDirectory[str], TestClient, Path]:
        """클라이언트 테스트가 후속 API 호출이나 명령 실행에 사용할 임시 리소스를 준비합니다.

        Returns:
            tuple[tempfile.TemporaryDirectory[str], TestClient, Path]: 정리 대상 임시 디렉터리, API 클라이언트, 작업공간 경로입니다.
        """
        directory = tempfile.TemporaryDirectory(prefix="alj-problem-studio-")
        workspace = Path(directory.name)
        return directory, TestClient(create_app(workspace)), workspace

    def sse_events(self, text: str) -> list[tuple[str, dict]]:
        """서버 전송 이벤트 응답 본문을 이벤트 이름과 JSON 페이로드 목록으로 파싱합니다.

        Args:
            text (str): 파일에 기록하거나 브라우저에서 기다릴 텍스트입니다.

        Returns:
            list[tuple[str, dict]]: 이벤트 이름과 JSON 페이로드를 순서대로 담은 목록입니다.
        """
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

    def poll_job(self, client: TestClient, job_id: str, terminal: bool = True) -> dict:
        """백그라운드 작업이 원하는 상태가 될 때까지 짧게 polling합니다."""
        current = {}
        for _ in range(100):
            response = client.get(f"/api/jobs/{job_id}")
            self.assertEqual(response.status_code, 200, response.text)
            current = response.json()
            if terminal and current["status"] not in {"queued", "running", "cancelling"}:
                return current
            if not terminal and current["status"] == "running":
                return current
            time.sleep(0.01)
        return current

    def test_static_ui_and_workspace_status(self) -> None:
        """정적 화면 및 작업공간 상태 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)

        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers.get("cache-control"), "no-store")
        self.assertIn("Problem Studio", page.text)
        self.assertIn("newProblemButton", page.text)
        self.assertIn("workspaceBuildAllButton", page.text)
        self.assertIn("workspaceBuildModal", page.text)
        self.assertIn("repositorySelect", page.text)
        self.assertIn("repositoryCloneButton", page.text)
        self.assertIn("repositoryRefreshButton", page.text)
        self.assertIn("repositoryModal", page.text)
        self.assertIn("unsavedChangesModal", page.text)
        self.assertIn("unsavedChangesSaveButton", page.text)
        self.assertIn("repositoryCloneStartButton", page.text)
        self.assertIn("repositoryOpenModal", page.text)
        self.assertIn("repositoryOpenSelect", page.text)
        self.assertIn("repositoryOpenStartButton", page.text)
        self.assertNotIn("repositoryRegisterButton", page.text)
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
        self.assertIn("problemFilterInput", page.text)
        self.assertIn("newProblemDefaultProfile", page.text)
        self.assertIn("newProblemUserTimeout", page.text)
        self.assertIn("deleteProblemModal", page.text)
        self.assertIn("deleteProblemConfirmInput", page.text)
        self.assertIn("문제 정보", page.text)
        self.assertIn("데이터 생성", page.text)
        self.assertIn("데이터 검증", page.text)
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
        self.assertIn("PyPy", page.text)
        self.assertIn("solutionCasesModal", page.text)
        self.assertIn("tabFeedbackPanel", page.text)
        self.assertIn("aggregateFeedbackPanel", page.text)
        self.assertIn("solutionStressModal", page.text)
        self.assertIn("solutionStressReviewModal", page.text)
        self.assertIn("solutionStressSelection", page.text)
        self.assertIn("solutionStressSelectionSummary", page.text)
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
        self.assertIn("jobCenterButton", page.text)
        self.assertIn("jobCenterDrawer", page.text)
        self.assertIn('role="complementary"', page.text)
        self.assertIn("jobCenterAnnouncements", page.text)
        self.assertIn("problemNavigationTitle", page.text)
        self.assertIn("검증/빌드", page.text)
        self.assertIn("솔루션 편집", page.text)
        self.assertIn("솔루션 파일 생성", page.text)
        self.assertIn("codemirror.min.js", page.text)
        self.assertIn("keymap/vim.min.js", page.text)
        self.assertIn('type="module" src="/static/app.js', page.text)
        self.assertNotIn("Link testlib.h", page.text)
        self.assertNotIn(">Diagnostics<", page.text)
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
        problem_list_css = client.get("/static/styles/problem-list.css")
        self.assertEqual(problem_list_css.status_code, 200)
        solution_rows_css = client.get("/static/styles/solution-rows.css")
        self.assertEqual(solution_rows_css.status_code, 200)
        module_texts = [
            script.text,
            state_module.text,
            api_module.text,
            sse_module.text,
            dom_module.text,
            storage_module.text,
        ]
        for path in [
            "/static/app/actions/build.js",
            "/static/app/actions/build-bulk.js",
            "/static/app/actions/build-locks.js",
            "/static/app/actions/build-status.js",
            "/static/app/actions/data.js",
            "/static/app/actions/files.js",
            "/static/app/actions/git.js",
            "/static/app/actions/pack-jobs.js",
            "/static/app/actions/problems.js",
            "/static/app/actions/repositories.js",
            "/static/app/actions/solution-artifacts.js",
            "/static/app/actions/solution-forms.js",
            "/static/app/actions/solutions.js",
            "/static/app/build-view.js",
            "/static/app/control-policy.js",
            "/static/app/events.js",
            "/static/app/feedback.js",
            "/static/app/jobs-view.js",
            "/static/app/loading.js",
            "/static/app/metadata-view.js",
            "/static/app/modal.js",
            "/static/app/unsaved-changes.js",
            "/static/app/progress.js",
            "/static/app/resources-view.js",
            "/static/app/results.js",
            "/static/app/solution-dirty.js",
            "/static/app/solution-status.js",
            "/static/app/tabs-view.js",
            "/static/app/view-persistence.js",
            "/static/app/workspace-view.js",
            "/static/app/editor/codemirror.js",
            "/static/app/editor/core.js",
            "/static/app/editor/dirty.js",
            "/static/app/editor/highlight.js",
            "/static/app/editor/history.js",
            "/static/app/editor/modal-codemirror.js",
            "/static/app/editor/selection.js",
            "/static/app/editor/visuals.js",
            "/static/app/editor/vim.js",
            "/static/app/editor/vim-context.js",
            "/static/app/editor/vim-mode.js",
            "/static/app/editor/vim-operations.js",
            "/static/app/editor/vim-registers.js",
        ]:
            module = client.get(path)
            self.assertEqual(module.status_code, 200, path)
            module_texts.append(module.text)
        script_text = "\n".join(module_texts)
        self.assertIn("export const state", state_module.text)
        self.assertIn("export async function api", api_module.text)
        self.assertIn("export function streamProgressDetail", sse_module.text)
        self.assertIn("export const optional", dom_module.text)
        self.assertIn("export function readStorage", storage_module.text)
        self.assertIn("function bindAppEvents", script_text)
        self.assertIn("function withLoading", script_text)
        self.assertIn("function deriveControlState", script_text)
        self.assertIn("function renderControlPolicies", script_text)
        self.assertIn('bindControlPolicy(casesButton, "solution.cases"', script_text)
        self.assertNotIn("function setControlsDisabled", script_text)
        self.assertNotIn("window.setTimeout(applyButtonPolicy", script_text)
        self.assertIn("function showAlert", script_text)
        self.assertIn("function recordTabFeedback", script_text)
        self.assertIn("function recordOperationFailure", script_text)
        self.assertIn(".pypy.", script_text)
        self.assertIn('language: "pypy"', script_text)
        self.assertIn("function renderFeedbackPanels", script_text)
        self.assertIn("function normalizeErrorDetail", api_module.text)
        self.assertIn("function confirmDiscardChanges", script_text)
        self.assertIn("function dirtySources", script_text)
        self.assertIn("function hasAnyUnsavedChanges", script_text)
        self.assertIn("function guardUnsavedTransition", script_text)
        self.assertIn("function saveDirtySources", script_text)
        self.assertIn("function discardDirtySources", script_text)
        self.assertIn("function requestCloseSurface", script_text)
        self.assertIn("pendingTransitionId", state_module.text)
        self.assertIn("savedCanonicalDraft", state_module.text)
        self.assertIn("problem.json 원본과 문제 정보 폼", script_text)
        self.assertIn("function beginProgress", script_text)
        self.assertIn("function setProgressStep", script_text)
        self.assertIn("function setProgressInsight", script_text)
        self.assertIn("function streamProgressDetail", sse_module.text)
        self.assertIn("function validateAllData", script_text)
        self.assertIn("function bindJobCenter", script_text)
        self.assertIn("function renderRepositoryOpenOptions", script_text)
        self.assertIn("function openSelectedRepositoryFromModal", script_text)
        self.assertIn("function updateRepositoryClonePreview", script_text)
        self.assertNotIn("/api/repositories/register", script_text)
        self.assertIn("function compactPath", script_text)
        self.assertIn("function pathDisclosureHtml", script_text)
        self.assertIn("ArrowRight", script_text)
        self.assertIn("authoringTabPanel", page.text)
        self.assertIn("function configureJobsView", script_text)
        self.assertIn("function syncJobCenterAccessibility", script_text)
        self.assertIn("function announceTerminalTransitions", script_text)
        self.assertIn("function trapFocusWithin", script_text)
        self.assertIn("function captureProblemListPosition", script_text)
        self.assertIn("function restoreProblemListPosition", script_text)
        self.assertIn("function revealSelectedProblemIfNeeded", script_text)
        self.assertIn('"(max-width: 1199px)"', script_text)
        self.assertIn("function jobOutcome", script_text)
        self.assertIn("function jobNeedsAttention", script_text)
        self.assertIn("failureDetails", script_text)
        self.assertIn("job-failure-detail", script_text)
        self.assertIn("job-log-list", script_text)
        self.assertIn("detail.problemId", script_text)
        self.assertIn("logs.slice().reverse()", script_text)
        self.assertIn("로그", script_text)
        self.assertIn("/api/jobs", script_text)
        self.assertIn("cancelBlockedReason", script_text)
        self.assertIn("모든 데이터 생성+검증", script_text)
        self.assertIn("function showLastRun", script_text)
        self.assertIn("function restoreProblemLastResult", script_text)
        self.assertIn("function storedLastResults", script_text)
        self.assertIn("function applyProblemMetadataToUi", script_text)
        self.assertIn("function updateMetadataPreview", script_text)
        self.assertIn("function positiveIntegerInput", script_text)
        self.assertIn("function metadataFormIssues", script_text)
        self.assertIn("function applyProblemRenameResult", script_text)
        self.assertIn("SAFE_PROBLEM_ID", state_module.text)
        self.assertIn("function renderMetadataValidation", script_text)
        self.assertIn("function metadataRawEditorDirty", script_text)
        self.assertIn("metadataToolGeneratorConfig", script_text)
        self.assertIn("metadataSolutionTimeout", script_text)
        self.assertIn("newProblemDefaultProfile", script_text)
        self.assertIn("function openDeleteProblemModal", script_text)
        self.assertIn("function deleteSelectedProblem", script_text)
        self.assertIn("function deleteSolution", script_text)
        self.assertIn("data-solution-delete", script_text)
        self.assertIn("DELETE_CONFIRM_PHRASE", script_text)
        self.assertIn("function folderLabel", script_text)
        self.assertIn("function toggleProblemFolder", script_text)
        self.assertIn("problemFolderCollapsed", state_module.text)
        self.assertIn("function updateBuildPanel", script_text)
        self.assertIn("function updateBuildDashboard", script_text)
        self.assertIn("function validationStatusForFile", script_text)
        self.assertIn("function errorKindForDetail", script_text)
        self.assertIn("function formatOperationFailure", script_text)
        self.assertIn("오류 유형", script_text)
        self.assertIn("Generator 런타임 오류", script_text)
        self.assertIn("resourceFilters", script_text)
        self.assertIn("function hasFreshFullTest", script_text)
        self.assertIn("PACK_OUTPUT_DIR", script_text)
        self.assertIn("function formatSolutionFailureSummary", script_text)
        self.assertIn("function failedSolutionChecks", script_text)
        self.assertIn("solutionCheckSource", script_text)
        self.assertIn("function renderSolutionValidationSummary", script_text)
        self.assertIn("function solutionValidationStatusForFile", script_text)
        self.assertIn("function openSolutionCasesModal", script_text)
        self.assertIn("function renderSolutionCasesBody", script_text)
        self.assertIn('"solutionStressModal"', script_text)
        self.assertIn('"solutionStressReviewModal"', script_text)
        self.assertIn('modal.classList.add("hidden")', script_text)
        self.assertIn('modal.setAttribute("aria-hidden", "true")', script_text)
        self.assertIn("function renderProblemSelectionState", script_text)
        self.assertIn("workspaceEmptyState", page.text)
        self.assertIn("첫 문제 만들기", page.text)
        self.assertIn('aria-labelledby="newProblemModalTitle"', page.text)
        self.assertIn("lastSolutionVerification", script_text)
        self.assertIn("function resetSolutionVerificationForRun", script_text)
        self.assertIn("function problemValidationStatus", script_text)
        self.assertIn("function selectedProblemBulkDiagnostic", script_text)
        self.assertIn("현재 문제 진단", script_text)
        self.assertIn("선택한 문제의 실패 단계와 상세만 표시합니다.", script_text)
        self.assertIn("problem-status-badge", script_text)
        self.assertIn("problem-status-failed", problem_list_css.text)
        self.assertIn("문제 있음", script_text)
        self.assertIn("resource-item.solution-row.verifying", solution_rows_css.text)
        self.assertIn("background: #f8fafc", solution_rows_css.text)
        self.assertIn("beforeunload", script_text)
        self.assertIn("aria-selected", script_text)
        self.assertIn("function createSolution", script_text)
        self.assertIn("function renameSolution", script_text)
        self.assertIn("function openSolutionEditModal", script_text)
        self.assertIn("function verifySingleSolution", script_text)
        self.assertIn('action.id === "uploadSolutions"', script_text)
        self.assertIn("encodeURIComponent(state.selectedProblem)", script_text)
        self.assertIn("activeSolutionVerification", state_module.text)
        self.assertIn("activeSolutionTestsByPath", state_module.text)
        self.assertIn("solutionTestResultsByPath", state_module.text)
        self.assertIn("function isFullSolutionVerificationActive", script_text)
        self.assertIn("/solutions/test/jobs", script_text)
        self.assertNotIn("function mergeSolutionVerification", script_text)
        self.assertIn("function highlightCode", script_text)
        self.assertIn("function initializeCodeMirror", script_text)
        self.assertIn("function initializeSourceModalEditors", script_text)
        self.assertIn("function modalEditorKeyForElement", script_text)
        self.assertIn("function focusModalEditor", script_text)
        self.assertIn("function syncModalEditorMode", script_text)
        self.assertIn("function modalEditorLanguage", script_text)
        self.assertIn("function getEditorValue", script_text)
        self.assertIn("function getModalEditorValue", script_text)
        self.assertIn("function forceHideLoading", script_text)
        self.assertIn("function handleCodeMirrorBeforeChange", script_text)
        self.assertIn("function handleCodeMirrorBeforeInput", script_text)
        self.assertIn("function handleEditorKeydown", script_text)
        self.assertIn("function handleVimKeydown", script_text)
        self.assertIn("function setEditorMode", script_text)
        self.assertIn("function updateEditorStatus", script_text)
        self.assertIn("function ensureEditorCursorVisible", script_text)
        self.assertIn("function enterVimVisualMode", script_text)
        self.assertIn("function handleVimVisualKey", script_text)
        self.assertIn("function vimCountValue", script_text)
        self.assertIn("function findVimSearch", script_text)
        self.assertIn("function undoEditorChange", script_text)
        self.assertIn("function currentPrimaryAction", script_text)
        self.assertIn("editorCommandInput", script_text)
        self.assertIn("function restoreEditorSettings", script_text)
        self.assertIn('const EDITOR_INDENT = "    "', state_module.text)
        self.assertIn("EDITOR_SETTINGS_KEY", state_module.text)
        self.assertIn("PERSISTED_VIEW_KEY", state_module.text)
        self.assertIn("function restoreViewPreference", script_text)
        self.assertIn("function runAllChecksOnce", script_text)
        self.assertIn("function withProblemTaskLock", script_text)
        self.assertIn("function shouldDisplayLastRunPanel", script_text)
        self.assertIn("function renderLastRunPanel", script_text)
        self.assertIn("navigator.locks", script_text)
        self.assertIn("PACK_JOB_KEY", state_module.text)
        self.assertIn("LAST_RESULTS_KEY", state_module.text)
        self.assertIn("PROBLEM_TASK_LOCK_NAME", state_module.text)
        self.assertIn("activePackJobsByProblem", state_module.text)
        self.assertIn("activePackJobForProblem", script_text)
        self.assertIn("locksByProblem", script_text)
        self.assertIn("jobsByProblem", script_text)
        self.assertIn("currentRunAllLock(problemId)", script_text)
        self.assertIn("function startPackBuild", script_text)
        self.assertIn("function startPackBuildOnce", script_text)
        self.assertIn("function buildPack", script_text)
        self.assertIn("function buildAllPacks", script_text)
        self.assertIn("function buildAllPacksOnce", script_text)
        self.assertIn("function openWorkspaceBuildModal", script_text)
        self.assertIn("function selectedBulkProblemIdsFromModal", script_text)
        self.assertIn("workspaceBuildAllButton", script_text)
        self.assertIn("function bulkBuildButtons", script_text)
        self.assertIn("manualProgress", script_text)
        self.assertIn("워커로 병렬 실행 중", sse_module.text)
        self.assertIn("/api/workspace/packs/build-all/stream", script_text)
        self.assertIn("전체 문제 테스트/팩 빌드", script_text)
        self.assertNotIn("문제 번호 순서를 확인하세요", script_text)
        self.assertIn("팩 빌드 전에 전체 테스트를 자동으로 실행합니다.", script_text)
        self.assertIn("전체 테스트를 통과하지 못해 팩 빌드를 중단했습니다.", script_text)
        self.assertIn("function pollPackJob", script_text)
        self.assertIn("function saveOpenFileIfDirty", script_text)
        self.assertIn("function roleForFile", script_text)
        self.assertIn("function runTabAction", script_text)
        self.assertIn("resource-role", script_text)
        self.assertIn("function solutionCheckMetrics", script_text)
        self.assertIn("function renderSolutionCaseRows", script_text)
        self.assertIn("function selectSolutionPath", script_text)
        self.assertIn("solutions-mode", script_text)
        self.assertIn("검증중", script_text)
        self.assertIn("개별 테스트 중", script_text)
        self.assertNotIn("maintainedCount", script_text)
        self.assertIn('panel.className = "solution-validation-summary hidden";', script_text)
        self.assertNotIn("Skipped ", script_text)
        self.assertNotIn("resultSummary", script_text)
        self.assertNotIn("resultOutput", script_text)
        self.assertNotIn("diagnosticsBoard", script_text)

        stylesheet = client.get("/static/styles.css")
        self.assertEqual(stylesheet.status_code, 200)
        style_texts = [stylesheet.text]
        for path in [
            "/static/styles/base.css",
            "/static/styles/sidebar.css",
            "/static/styles/layout.css",
            "/static/styles/tabs.css",
            "/static/styles/tabs-top.css",
            "/static/styles/workspace-layout.css",
            "/static/styles/problem-list.css",
            "/static/styles/build-dashboard.css",
            "/static/styles/editor-settings.css",
            "/static/styles/task-panel.css",
            "/static/styles/metadata.css",
            "/static/styles/resources.css",
            "/static/styles/resource-list.css",
            "/static/styles/solution-rows.css",
            "/static/styles/solution-cases.css",
            "/static/styles/solution-artifacts.css",
            "/static/styles/solution-validation.css",
            "/static/styles/editor.css",
            "/static/styles/feedback.css",
            "/static/styles/dialogs.css",
            "/static/styles/jobs.css",
            "/static/styles/responsive.css",
        ]:
            style_module = client.get(path)
            self.assertEqual(style_module.status_code, 200, path)
            style_texts.append(style_module.text)
        stylesheet_text = "\n".join(style_texts)
        self.assertIn('@import url("./styles/base.css', stylesheet_text)
        codemirror = client.get("/static/vendor/codemirror/codemirror.min.js")
        self.assertEqual(codemirror.status_code, 200)
        self.assertIn("CodeMirror", codemirror.text)
        self.assertIn("body.sidebar-open .sidebar", stylesheet_text)
        self.assertIn(".problem-navigation", stylesheet_text)
        self.assertIn("overscroll-behavior: contain", stylesheet_text)
        self.assertIn(
            "grid-template-rows: auto auto auto auto auto minmax(96px, 1fr)", stylesheet_text
        )
        self.assertIn("@media (max-width: 1199px)", stylesheet_text)
        self.assertIn(".job-cancel-reason", stylesheet_text)
        self.assertIn(".job-row.attention", stylesheet_text)
        self.assertIn(".job-failure-detail", stylesheet_text)
        self.assertIn(".job-log-list", stylesheet_text)
        self.assertIn("#jobCenterCloseButton", stylesheet_text)
        self.assertIn("z-index: 10040", stylesheet_text)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", stylesheet_text)
        self.assertIn(".mobile-header-copy", stylesheet_text)
        self.assertIn(".mobile-header-meta", stylesheet_text)
        self.assertIn(".tab-marker", stylesheet_text)
        self.assertIn(".tab-hint", stylesheet_text)
        self.assertIn(".editor-settings-panel", stylesheet_text)
        self.assertIn(".segmented-control", stylesheet_text)
        self.assertIn(".editor-mode-badge", stylesheet_text)
        self.assertIn(".editor-status-bar", stylesheet_text)
        self.assertIn(".editor-command-line", stylesheet_text)
        self.assertIn("white-space: pre-wrap", stylesheet_text)
        self.assertIn("width: min(720px", stylesheet_text)
        self.assertIn("body.sidebar-open .sidebar-toggle-icon", stylesheet_text)
        self.assertIn("transform: translateX(-102%)", stylesheet_text)
        self.assertIn(".app-alert", stylesheet_text)
        self.assertIn(".tab-feedback-panel", stylesheet_text)
        self.assertIn(".tab-feedback-item", stylesheet_text)
        self.assertIn(".problem-folder", stylesheet_text)
        self.assertIn(".problem-folder-section", stylesheet_text)
        self.assertIn(".metadata-card", stylesheet_text)
        self.assertIn(".metadata-limit-grid", stylesheet_text)
        self.assertIn(".number-with-unit", stylesheet_text)
        self.assertIn(".metadata-details", stylesheet_text)
        self.assertIn(".metadata-validation-summary", stylesheet_text)
        self.assertIn(".studio-layout.info-mode", stylesheet_text)
        self.assertIn(".danger-note", stylesheet_text)
        self.assertIn("button.danger", stylesheet_text)
        self.assertIn(".field-error", stylesheet_text)
        self.assertIn(".global-task-status", stylesheet_text)
        self.assertIn(".resource-role", stylesheet_text)
        self.assertIn(".solution-validation-summary", stylesheet_text)
        self.assertIn(".solution-row-main", stylesheet_text)
        self.assertIn(".solution-metric-strip", stylesheet_text)
        self.assertIn(".studio-layout.solutions-mode .action-grid", stylesheet_text)
        self.assertIn("max-width: none", stylesheet_text)
        self.assertIn("clip-path: inset(50%)", stylesheet_text)
        self.assertIn(".solution-case-table", stylesheet_text)
        self.assertIn(".solution-case-row", stylesheet_text)
        self.assertIn(".solution-cases-modal", stylesheet_text)
        self.assertIn(".solution-cases-summary", stylesheet_text)
        self.assertIn(".solution-editor-modal", stylesheet_text)
        self.assertIn(".source-modal-editor", stylesheet_text)
        self.assertIn(".modal-editor-toolbar", stylesheet_text)
        self.assertIn(".source-modal-codemirror", stylesheet_text)
        self.assertIn(".studio-codemirror", stylesheet_text)
        self.assertIn(".studio-codemirror .cm-meta", stylesheet_text)
        self.assertIn(".studio-codemirror .cm-def", stylesheet_text)
        self.assertIn(".solution-validation-detail-row", stylesheet_text)
        self.assertIn(".solution-validation-failure", stylesheet_text)
        self.assertIn(".resource-item.mismatch", stylesheet_text)
        self.assertIn(".resource-item.match", stylesheet_text)
        self.assertIn(".resource-item.match.active", stylesheet_text)
        self.assertIn(".resource-item.mismatch.active", stylesheet_text)
        self.assertIn(".progress-steps", stylesheet_text)
        self.assertIn(".progress-insight", stylesheet_text)
        self.assertIn(".progress-summary", stylesheet_text)
        self.assertIn(".last-run-panel", stylesheet_text)
        self.assertNotIn(".result-panel", stylesheet_text)
        self.assertNotIn(".progress-log", stylesheet_text)
        self.assertNotIn(".debug-log", stylesheet_text)

        status = client.get("/api/workspace")
        self.assertEqual(status.status_code, 200, status.text)
        data = status.json()
        self.assertEqual(Path(data["workspace"]), workspace.resolve())
        self.assertEqual(data["problemCount"], 0)
        self.assertEqual(data["problems"], [])
        self.assertEqual(data["folders"], [])
        self.assertNotIn("warning", data)

    def test_workspace_status_warns_for_non_local_binding_policy(self) -> None:
        """작업공간 상태 경고 비 로컬 바인딩 정책 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory = tempfile.TemporaryDirectory(prefix="alj-problem-studio-warning-")
        self.addCleanup(directory.cleanup)
        workspace = Path(directory.name)
        client = TestClient(create_app(workspace, git_write_enabled=False, workspace_warning=True))

        status = client.get("/api/workspace")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()["warning"]["kind"], "nonLocalBinding")
        self.assertIn("기본 차단", status.json()["warning"]["message"])
        self.assertFalse(status.json()["writeEnabled"])

        created = client.post("/api/problems", json={"problem_id": "01", "title": "Warn"})
        self.assertEqual(created.status_code, 403, created.text)

    def test_create_edit_compile_and_list_solutions(self) -> None:
        """생성 편집 컴파일 및 목록 솔루션 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, workspace = self.make_client()
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

        blocked_reference_delete = client.request(
            "DELETE",
            "/api/problems/alpha/solutions",
            json={"path": "solutions/main_solution.ac.cpp"},
        )
        self.assertEqual(
            blocked_reference_delete.status_code,
            400,
            blocked_reference_delete.text,
        )
        self.assertIn(
            "cannot delete reference solution",
            blocked_reference_delete.json()["detail"],
        )
        self.assertTrue(
            (workspace / "problems" / "alpha" / "solutions" / "main_solution.ac.cpp").exists()
        )

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

        created_pypy_solution = client.post(
            "/api/problems/alpha/solutions/create",
            json={"name": "slow_solution", "expected": "tle", "language": "pypy"},
        )
        self.assertEqual(created_pypy_solution.status_code, 200, created_pypy_solution.text)
        self.assertEqual(
            created_pypy_solution.json()["created"]["path"],
            "solutions/slow_solution.pypy.tle.py",
        )
        pypy_file = client.get("/api/problems/alpha/files/solutions/slow_solution.pypy.tle.py")
        self.assertEqual(pypy_file.status_code, 200, pypy_file.text)
        self.assertIn("def main", pypy_file.json()["content"])

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

        deleted_solution = client.request(
            "DELETE",
            "/api/problems/alpha/solutions",
            json={"path": "solutions/renamed_solution.wa.py"},
        )
        self.assertEqual(deleted_solution.status_code, 200, deleted_solution.text)
        self.assertEqual(
            deleted_solution.json()["deleted"]["path"],
            "solutions/renamed_solution.wa.py",
        )
        self.assertFalse(
            (workspace / "problems" / "alpha" / "solutions" / "renamed_solution.wa.py").exists()
        )
        remaining_files = {item["path"] for item in deleted_solution.json()["files"]}
        self.assertNotIn("solutions/renamed_solution.wa.py", remaining_files)

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
        self.assertNotIn("solutions", mocked_verify.call_args.kwargs)
        self.assertEqual(result["scope"], "all")

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
        ) as mocked_test:
            test_job = client.post(
                "/api/problems/alpha/solutions/test/jobs",
                json={"profile": "hidden", "solution": "solutions/reference.ac.cpp"},
            )

        self.assertEqual(test_job.status_code, 200, test_job.text)
        finished = test_job.json()
        for _ in range(50):
            job_response = client.get(f"/api/jobs/{test_job.json()['jobId']}")
            self.assertEqual(job_response.status_code, 200, job_response.text)
            finished = job_response.json()
            if finished["status"] not in {"queued", "running", "cancelling"}:
                break
            time.sleep(0.01)
        self.assertEqual(finished["kind"], "solution-test")
        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(finished["result"]["scope"], "single")
        self.assertEqual(finished["result"]["solution"], "solutions/reference.ac.cpp")
        self.assertEqual(
            mocked_test.call_args.kwargs["solutions"],
            ["solutions/reference.ac.cpp"],
        )

        backup_reference = client.post(
            "/api/problems/alpha/solutions/create",
            json={"name": "backup_reference", "expected": "ac", "language": "cpp"},
        )
        self.assertEqual(backup_reference.status_code, 200, backup_reference.text)
        deleted_reference = client.request(
            "DELETE",
            "/api/problems/alpha/solutions",
            json={"path": "solutions/reference.ac.cpp"},
        )
        self.assertEqual(deleted_reference.status_code, 200, deleted_reference.text)
        self.assertTrue(deleted_reference.json()["referenceChanged"])
        self.assertEqual(
            deleted_reference.json()["metadata"]["tools"]["solution"],
            "solutions/backup_reference.ac.cpp",
        )
        self.assertFalse(
            (workspace / "problems" / "alpha" / "solutions" / "reference.ac.cpp").exists()
        )

    def test_solution_verify_job_exposes_partial_check_progress(self) -> None:
        """솔루션 전체 검증 job은 완료 전에도 끝난 솔루션 결과를 progress에 노출해야 합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Partial"})
        partial_ready = threading.Event()
        finish = threading.Event()

        def fake_verify_solutions(*args, on_check=None, **kwargs) -> dict:
            self.assertEqual(kwargs["max_workers"], 4)
            check = SolutionCheckResult(
                source=workspace / "problems" / "alpha" / "solutions" / "main_solution.ac.cpp",
                expected_status="accepted",
                actual_status="accepted",
                raw_actual_status="accepted",
                run_id="partial-run",
                passed=True,
                cases=[{"case": "001", "status": "ok"}],
                metrics={"maxTimeMs": 1},
                status_evidence={
                    "rawStatus": "accepted",
                    "rankedStatus": "accepted",
                    "caseStatusCounts": {"accepted": 1},
                },
            )
            if on_check is not None:
                on_check(check, 1, 1)
            partial_ready.set()
            finish.wait(2)
            return {
                "problemId": "alpha",
                "profile": "hidden",
                "passed": True,
                "verifiedCount": 1,
                "totalCount": 1,
                "skippedCount": 0,
                "checks": [check.to_dict(workspace)],
            }

        with patch(
            "problem_studio.web.routes.solutions.verify_solutions",
            side_effect=fake_verify_solutions,
        ):
            started = client.post(
                "/api/problems/alpha/solutions/verify/jobs",
                json={"profile": "hidden"},
            )
            self.assertEqual(started.status_code, 200, started.text)
            self.assertEqual(started.json()["target"]["maxWorkers"], 4)
            job_id = started.json()["jobId"]
            self.assertTrue(partial_ready.wait(2))
            running = self.poll_job(client, job_id, terminal=False)
            progress = running["progress"]
            self.assertEqual(progress["current"], 1)
            self.assertEqual(progress["total"], 1)
            self.assertEqual(progress["partialSummary"]["verifiedCount"], 1)
            self.assertEqual(progress["partialSummary"]["failedCount"], 0)
            self.assertEqual(
                progress["partialCheck"]["source"],
                "problems/alpha/solutions/main_solution.ac.cpp",
            )
            self.assertEqual(progress["partialCheck"]["actualStatus"], "accepted")
            finish.set()
            finished = self.poll_job(client, job_id)

        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(finished["result"]["checks"][0]["runId"], "partial-run")

    def test_solution_verify_job_exposes_failed_outcome_for_mismatches(self) -> None:
        """실제 솔루션 검증 job API는 mismatch 결과를 succeeded 상태의 failed outcome으로 노출해야 합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Mismatch"})

        def fake_verify_solutions(*args, **kwargs) -> dict:
            check = SolutionCheckResult(
                source=workspace / "problems" / "alpha" / "solutions" / "wrong.wa.cpp",
                expected_status="wrong_answer",
                actual_status="accepted",
                raw_actual_status="accepted",
                run_id="mismatch-run",
                passed=False,
                cases=[],
                metrics={},
                status_evidence={
                    "rawStatus": "accepted",
                    "rankedStatus": "accepted",
                    "caseStatusCounts": {},
                },
                message="expected WA but accepted",
            )
            return {
                "problemId": "alpha",
                "profile": "hidden",
                "passed": False,
                "verifiedCount": 1,
                "totalCount": 1,
                "skippedCount": 0,
                "checks": [check.to_dict(workspace)],
            }

        with patch(
            "problem_studio.web.routes.solutions.verify_solutions",
            side_effect=fake_verify_solutions,
        ):
            started = client.post(
                "/api/problems/alpha/solutions/verify/jobs",
                json={"profile": "hidden"},
            )
            self.assertEqual(started.status_code, 200, started.text)
            finished = self.poll_job(client, started.json()["jobId"])

        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(finished["outcome"], "failed")
        self.assertEqual(finished["failureStage"], "solutions")
        self.assertEqual(
            finished["failureDetails"][0]["source"], "problems/alpha/solutions/wrong.wa.cpp"
        )
        self.assertIn("expected WA but accepted", finished["failureDetails"][0]["message"])

    def test_solution_verify_job_passes_cancel_check_to_service(self) -> None:
        """솔루션 검증 job 취소는 서비스 계층의 cancel_check까지 전달되어야 합니다."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Cancel"})
        started = threading.Event()
        release = threading.Event()

        def fake_verify_solutions(*args, cancel_check=None, **kwargs) -> dict:
            self.assertIsNotNone(cancel_check)
            started.set()
            release.wait(2)
            cancel_check()
            return {
                "problemId": "alpha",
                "profile": "hidden",
                "passed": True,
                "verifiedCount": 0,
                "totalCount": 0,
                "skippedCount": 0,
                "checks": [],
            }

        with patch(
            "problem_studio.web.routes.solutions.verify_solutions",
            side_effect=fake_verify_solutions,
        ):
            response = client.post(
                "/api/problems/alpha/solutions/verify/jobs",
                json={"profile": "hidden", "max_workers": 4},
            )
            self.assertEqual(response.status_code, 200, response.text)
            job_id = response.json()["jobId"]
            self.assertTrue(started.wait(1))
            cancelled = client.post(f"/api/jobs/{job_id}/cancel")
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertTrue(cancelled.json()["cancelRequested"])
            release.set()
            finished = self.poll_job(client, job_id)

        self.assertEqual(finished["status"], "cancelled")
        self.assertTrue(finished["cancelSupported"])

    def test_full_checks_job_uses_parallel_solution_verify_and_partial_progress(self) -> None:
        """전체 테스트 job의 솔루션 검증도 병렬 worker와 부분 결과 progress를 사용해야 합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Checks"})
        verify_kwargs = {}

        def fake_verify_solutions(*args, on_check=None, **kwargs) -> dict:
            verify_kwargs.update(kwargs)
            self.assertIsNotNone(kwargs.get("cancel_check"))
            check = SolutionCheckResult(
                source=workspace / "problems" / "alpha" / "solutions" / "main_solution.ac.cpp",
                expected_status="accepted",
                actual_status="accepted",
                raw_actual_status="accepted",
                run_id="full-check-run",
                passed=True,
                cases=[{"case": "001", "status": "ok"}],
                metrics={"maxTimeMs": 1},
                status_evidence={
                    "rawStatus": "accepted",
                    "rankedStatus": "accepted",
                    "caseStatusCounts": {"accepted": 1},
                },
            )
            if on_check is not None:
                on_check(check, 1, 1)
            return {
                "problemId": "alpha",
                "profile": "hidden",
                "passed": True,
                "verifiedCount": 1,
                "totalCount": 1,
                "skippedCount": 0,
                "checks": [check.to_dict(workspace)],
            }

        with (
            patch("problem_studio.web.routes.checks.compile_cases", return_value={"valid": True}),
            patch(
                "problem_studio.web.routes.checks.compile_problem_tools",
                return_value={"checker": workspace / "checker"},
            ),
            patch(
                "problem_studio.web.routes.checks.validate_all_data",
                return_value={"caseCount": 1},
            ),
            patch(
                "problem_studio.web.routes.checks.verify_solutions",
                side_effect=fake_verify_solutions,
            ),
        ):
            response = client.post("/api/problems/alpha/checks/jobs", json={"force": True})
            self.assertEqual(response.status_code, 200, response.text)
            finished = self.poll_job(client, response.json()["jobId"])

        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(verify_kwargs["max_workers"], 4)
        progress = finished["progress"]
        self.assertEqual(progress["partialSummary"]["verifiedCount"], 1)
        self.assertEqual(progress["partialSummary"]["maxWorkers"], 4)
        self.assertEqual(progress["partialCheck"]["runId"], "full-check-run")

    def test_problem_delete_requires_exact_confirmation(self) -> None:
        """문제 삭제 요구 정확한 확인 문구 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """testlib 링크 및 경로 안전성 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """빌드 패키지 사용 작업공간 패키지 출력 디렉터리 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """검증 솔루션 사용 샘플 워밍업 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """검증 스트림 생성 모든 프로필 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
            """실제 생성 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

            Args:
                problem_id (Any): 테스트가 생성하거나 조회할 문제 식별자입니다.
                profile (Any): 검증이나 실행에 사용할 테스트 프로필 이름입니다.
                force (Any): 캐시나 기존 산출물을 무시하고 다시 처리할지 결정하는 플래그입니다.
                root (Any): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.
                progress (Any): 가짜 실행기가 진행 로그를 전달할 콜백입니다.

            Returns:
                Any: 테스트 대상 API가 실제 실행 결과처럼 소비할 수 있는 결정적 결과 데이터입니다.
            """
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
        """패키지 빌드 가능 실행 백그라운드 작업 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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

    def test_pack_build_jobs_can_be_stale_and_dismissed(self) -> None:
        """패키지 빌드 작업 가능 오래된 및 정리 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.app.state.jobs = BackgroundJobStore(ttl_seconds=0, max_jobs=5)
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
        ):
            started = client.post(
                "/api/problems/01/packs/build",
                json={"pack_id": "basic", "verify_profile": "hidden"},
            )

        job_id = started.json()["jobId"]
        status = {}
        for _ in range(50):
            polled = client.get(f"/api/problems/01/packs/jobs/{job_id}")
            self.assertEqual(polled.status_code, 200, polled.text)
            status = polled.json()
            if status["status"] == "stale":
                break
            time.sleep(0.01)

        self.assertEqual(status["status"], "stale")
        self.assertTrue(status["stale"])
        self.assertEqual(status["previousStatus"], "succeeded")
        self.assertIsNotNone(status["expiresAt"])
        listed = client.get("/api/problems/01/packs/jobs")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["jobs"][0]["jobId"], job_id)
        download = client.get(f"/api/problems/01/packs/jobs/{job_id}/download")
        self.assertEqual(download.status_code, 409, download.text)
        self.assertIn("stale", download.json()["detail"])

        dismissed = client.delete(f"/api/problems/01/packs/jobs/{job_id}")
        self.assertEqual(dismissed.status_code, 200, dismissed.text)
        missing = client.get(f"/api/problems/01/packs/jobs/{job_id}")
        self.assertEqual(missing.status_code, 404, missing.text)

    def test_pack_build_job_can_be_cancelled(self) -> None:
        """패키지 빌드 작업 가능 취소 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "01", "title": "Pack"})
        started_event = threading.Event()
        release = threading.Event()

        def slow_build(*args, cancel_token=None, **kwargs) -> dict:
            """느린 빌드 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.
                kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
            started_event.set()
            release.wait(timeout=2)
            if cancel_token:
                cancel_token.check()
            return {"archiveLabel": "dist/packs/basic.aljpack", "problems": ["01"]}

        with patch("problem_studio.web.routes.packs.build_problem_pack", side_effect=slow_build):
            started = client.post(
                "/api/problems/01/packs/build",
                json={"pack_id": "basic", "verify_profile": "hidden"},
            )
            self.assertEqual(started.status_code, 200, started.text)
            job_id = started.json()["jobId"]
            self.assertTrue(started_event.wait(timeout=1))

            active_dismiss = client.delete(f"/api/problems/01/packs/jobs/{job_id}")
            self.assertEqual(active_dismiss.status_code, 409, active_dismiss.text)

            cancelled = client.post(f"/api/problems/01/packs/jobs/{job_id}/cancel")
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertTrue(cancelled.json()["cancelRequested"])
            release.set()

            status = {}
            for _ in range(50):
                polled = client.get(f"/api/problems/01/packs/jobs/{job_id}")
                self.assertEqual(polled.status_code, 200, polled.text)
                status = polled.json()
                if status["status"] == "cancelled":
                    break
                time.sleep(0.01)

        self.assertEqual(status["status"], "cancelled")
        self.assertTrue(status["cancelSupported"])

    def test_workspace_bulk_pack_build_can_run_as_cancellable_job(self) -> None:
        """작업공간 일괄 패키지 빌드 가능 실행 취소 가능 작업 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        started_event = threading.Event()
        release = threading.Event()

        def slow_bulk(*args, cancel_token=None, **kwargs) -> dict:
            """느린 일괄 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.
                kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
            started_event.set()
            release.wait(timeout=2)
            if cancel_token:
                cancel_token.check()
            return {"passed": True, "summary": "ok", "problemCount": 0, "problems": []}

        with patch(
            "problem_studio.web.routes.bulk.build_all_problem_packs", side_effect=slow_bulk
        ):
            started = client.post(
                "/api/workspace/packs/build-all",
                json={
                    "pack_id": "basic",
                    "verify_profile": "hidden",
                    "force": True,
                    "problem_ids": ["01"],
                },
            )
            self.assertEqual(started.status_code, 200, started.text)
            job_id = started.json()["jobId"]
            self.assertEqual(started.json()["kind"], "workspace-pack-build")
            self.assertTrue(started_event.wait(timeout=1))

            active_dismiss = client.delete(f"/api/workspace/packs/jobs/{job_id}")
            self.assertEqual(active_dismiss.status_code, 409, active_dismiss.text)

            cancelled = client.post(f"/api/workspace/packs/jobs/{job_id}/cancel")
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertTrue(cancelled.json()["cancelRequested"])
            release.set()

            status = {}
            for _ in range(50):
                polled = client.get(f"/api/workspace/packs/jobs/{job_id}")
                self.assertEqual(polled.status_code, 200, polled.text)
                status = polled.json()
                if status["status"] == "cancelled":
                    break
                time.sleep(0.01)

        self.assertEqual(status["status"], "cancelled")
        self.assertTrue(status["cancelSupported"])

    def test_background_job_store_retains_recent_completed_jobs(self) -> None:
        """백그라운드 작업 저장소 보존 최근 완료된 작업 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        jobs = BackgroundJobStore(max_jobs=2)
        for index in range(3):
            jobs.start(
                kind="test",
                title=f"job {index}",
                problem_id="01",
                operation=lambda index=index: {"index": index},
            )

        for _ in range(50):
            retained = jobs.list()
            if len(retained) == 2 and all(job.status != "running" for job in retained):
                break
            time.sleep(0.01)

        self.assertEqual(len(jobs.list()), 2)

    def test_background_job_store_can_cancel_running_job(self) -> None:
        """백그라운드 작업 저장소 가능 취소 실행 중 작업 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        jobs = BackgroundJobStore(max_jobs=5)
        started = threading.Event()
        release = threading.Event()

        def operation(cancel_token) -> dict:
            """작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
            started.set()
            release.wait(timeout=2)
            cancel_token.check()
            return {"ok": True}

        job = jobs.start(
            kind="test",
            title="job",
            problem_id="01",
            operation=operation,
            cancel_supported=True,
        )
        self.assertTrue(started.wait(timeout=1))
        self.assertTrue(jobs.cancel(job.job_id))
        release.set()

        for _ in range(50):
            current = jobs.get(job.job_id)
            if current and current.status == "cancelled":
                break
            time.sleep(0.01)

        current = jobs.get(job.job_id)
        self.assertIsNotNone(current)
        self.assertEqual(current.status, "cancelled")
        data = jobs.job_dict(current)
        self.assertTrue(data["cancelSupported"])
        self.assertTrue(data["cancelRequested"])
        self.assertEqual(data["status"], "cancelled")

    def test_background_job_store_rejects_cancel_for_non_cancellable_job(self) -> None:
        """백그라운드 작업 저장소 거부 취소 비 취소 가능 작업 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        jobs = BackgroundJobStore(max_jobs=5)
        job = jobs.start(
            kind="test",
            title="job",
            problem_id="01",
            operation=lambda: {"ok": True},
        )

        self.assertFalse(jobs.cancel(job.job_id))

    def test_background_job_store_limits_running_jobs(self) -> None:
        """백그라운드 작업 저장소 제한 실행 중 작업 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        jobs = BackgroundJobStore(max_jobs=5, max_running_jobs=1)
        started = threading.Event()
        release = threading.Event()
        second_started = threading.Event()

        def operation() -> dict:
            """작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
            started.set()
            release.wait(timeout=2)
            return {"ok": True}

        first = jobs.start(kind="test", title="one", problem_id="01", operation=operation)
        self.assertTrue(started.wait(timeout=1))
        self.assertEqual(jobs.running_count(), 1)
        second = jobs.start(
            kind="test",
            title="two",
            problem_id="01",
            operation=lambda: second_started.set() or {"ok": True},
        )
        self.assertEqual(second.status, "queued")
        self.assertEqual(jobs.queued_count(), 1)
        release.set()

        for _ in range(50):
            current = jobs.get(first.job_id)
            if current and current.status == "succeeded" and second_started.is_set():
                break
            time.sleep(0.01)

        self.assertEqual(jobs.running_count(), 0)
        self.assertEqual(jobs.get(second.job_id).status, "succeeded")

    def test_background_job_store_exposes_failed_outcome_for_domain_failures(self) -> None:
        """작업이 예외 없이 끝나도 result가 실패이면 작업 센터가 실패성 결과로 분류할 수 있어야 합니다."""
        jobs = BackgroundJobStore(max_jobs=5)
        job = jobs.start(
            kind="solution-verify",
            title="기대 결과 검증",
            problem_id="alpha",
            operation=lambda: {
                "passed": False,
                "failureStage": "solutions",
                "failureStageLabel": "솔루션 기대 결과",
                "failureDetails": [
                    {
                        "label": "솔루션 기대 결과",
                        "source": "solutions/wrong.wa.cpp",
                        "expectedStatus": "wrong_answer",
                        "actualStatus": "accepted",
                        "message": "expected WA but accepted",
                    }
                ],
            },
        )

        for _ in range(50):
            current = jobs.get(job.job_id)
            if current and current.status == "succeeded":
                break
            time.sleep(0.01)

        data = jobs.job_dict(jobs.get(job.job_id))
        self.assertEqual(data["status"], "succeeded")
        self.assertEqual(data["outcome"], "failed")
        self.assertEqual(data["failureStage"], "solutions")
        self.assertEqual(data["failureStageLabel"], "솔루션 기대 결과")
        self.assertEqual(data["failureDetails"][0]["source"], "solutions/wrong.wa.cpp")
        self.assertEqual(data["errorKind"], "validation-mismatch")

    def test_background_job_store_exposes_exception_failure_details(self) -> None:
        """예외로 끝난 작업은 최근 진행 단계와 오류를 작업 센터 상세 정보로 노출해야 합니다."""
        jobs = BackgroundJobStore(max_jobs=5, max_running_jobs=1)
        release = threading.Event()
        blocker = jobs.start(
            kind="blocker",
            title="blocker",
            problem_id="alpha",
            operation=lambda: release.wait(timeout=2) or {"ok": True},
        )
        while jobs.get(blocker.job_id).status != "running":
            time.sleep(0.01)

        def operation() -> dict:
            jobs.update_progress(
                job.job_id,
                "Compiling checker tool.",
                label="도구 컴파일",
                extra={"failureStage": "tools"},
            )
            raise JudgeError("checker compile failed")

        job = jobs.start(
            kind="tools-compile",
            title="도구 컴파일",
            problem_id="alpha",
            target={"problemId": "alpha", "tool": "checker"},
            operation=operation,
        )
        release.set()

        for _ in range(50):
            current = jobs.get(job.job_id)
            if current and current.status == "failed":
                break
            time.sleep(0.01)

        data = jobs.job_dict(jobs.get(job.job_id))
        self.assertEqual(data["outcome"], "failed")
        self.assertEqual(data["errorKind"], "exception")
        self.assertEqual(data["failureStage"], "tools")
        self.assertEqual(data["failureDetails"][0]["label"], "도구 컴파일")
        self.assertIn("checker compile failed", data["failureDetails"][0]["message"])

    def test_background_job_store_infers_stage_and_handles_empty_exception_message(self) -> None:
        """명시 stage가 없어도 진행 메시지와 빈 예외에서 실패 상세를 복원해야 합니다."""
        jobs = BackgroundJobStore(max_jobs=5, max_running_jobs=1)
        release = threading.Event()
        blocker = jobs.start(
            kind="blocker",
            title="blocker",
            problem_id="alpha",
            operation=lambda: release.wait(timeout=2) or {"ok": True},
        )
        while jobs.get(blocker.job_id).status != "running":
            time.sleep(0.01)

        def operation() -> dict:
            jobs.update_progress(job.job_id, "Building pack basic for problem alpha.")
            raise AssertionError()

        job = jobs.start(
            kind="pack-build",
            title="팩 빌드",
            problem_id="alpha",
            operation=operation,
        )
        release.set()

        for _ in range(50):
            current = jobs.get(job.job_id)
            if current and current.status == "failed":
                break
            time.sleep(0.01)

        data = jobs.job_dict(jobs.get(job.job_id))
        self.assertEqual(data["outcome"], "failed")
        self.assertEqual(data["failureStage"], "pack")
        self.assertEqual(data["errorKind"], "exception")
        self.assertIn("AssertionError", data["failureDetails"][0]["message"])

    def test_background_job_store_flattens_nested_problem_failure_details(self) -> None:
        """workspace job의 문제별 실패 상세는 상위 작업 센터 row에서도 바로 보여야 합니다."""
        jobs = BackgroundJobStore(max_jobs=5)
        job = jobs.start(
            kind="workspace-pack-build",
            title="전체 문제 테스트/팩 빌드",
            problem_id=WORKSPACE_JOB_PROBLEM_ID,
            operation=lambda: {
                "passed": False,
                "failedCount": 1,
                "summary": "2개 중 1개 문제 실패",
                "problems": [
                    {"problemId": "alpha", "passed": True},
                    {
                        "problemId": "beta",
                        "passed": False,
                        "failureStage": "solutions",
                        "failureStageLabel": "솔루션 기대 결과",
                        "failureDetails": [
                            {
                                "label": "솔루션 기대 결과",
                                "source": "solutions/wrong.wa.cpp",
                                "message": "expected mismatch",
                            }
                        ],
                    },
                ],
            },
        )

        for _ in range(50):
            current = jobs.get(job.job_id)
            if current and current.status == "succeeded":
                break
            time.sleep(0.01)

        data = jobs.job_dict(jobs.get(job.job_id))
        self.assertEqual(data["outcome"], "failed")
        self.assertEqual(data["failureStage"], "solutions")
        self.assertEqual(data["failureDetails"][0]["problemId"], "beta")
        self.assertEqual(data["failureDetails"][0]["source"], "solutions/wrong.wa.cpp")

    def test_enqueue_background_job_allows_immediate_progress_without_id_race(self) -> None:
        """Problem Studio job helper는 작업 시작 직후 progress를 호출해도 job id 초기화 race가 없어야 합니다."""
        jobs = BackgroundJobStore(max_jobs=5)

        def operation(cancel_token: CancelToken, progress) -> dict:
            progress("first progress", label="초기 단계")
            cancel_token.check()
            return {"passed": True}

        job = enqueue_background_job(
            jobs,
            kind="race-check",
            title="race",
            problem_id="alpha",
            lane="test:alpha",
            target={"problemId": "alpha"},
            operation=operation,
        )

        for _ in range(50):
            current = jobs.get(job.job_id)
            if current and current.status == "succeeded":
                break
            time.sleep(0.01)

        data = jobs.job_dict(jobs.get(job.job_id))
        self.assertEqual(data["status"], "succeeded")
        self.assertEqual(data["outcome"], "passed")
        self.assertEqual(data["progress"]["message"], "first progress")

    def test_pack_build_job_uses_shared_diagnostics_for_failures(self) -> None:
        """단일 pack build도 공통 작업 진단 경로를 사용해 실패 단계를 pack으로 노출해야 합니다."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Pack"})

        def fail_pack_build(*args, **kwargs):
            raise JudgeError("pack artifact failed")

        with patch(
            "problem_studio.web.routes.packs.build_problem_pack",
            side_effect=fail_pack_build,
        ):
            started = client.post(
                "/api/problems/alpha/packs/build",
                json={"pack_id": "basic", "verify_profile": "hidden"},
            )
            self.assertEqual(started.status_code, 200, started.text)
            finished = self.poll_job(client, started.json()["jobId"])

        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["outcome"], "failed")
        self.assertEqual(finished["failureStage"], "pack")
        self.assertEqual(finished["failureStageLabel"], "팩 생성")
        self.assertIn("pack artifact failed", finished["failureDetails"][0]["message"])

    def test_cold_workspace_first_and_second_check_and_pack_jobs_succeed(self) -> None:
        """새 workspace에서 첫 번째/두 번째 전체 테스트와 pack build job이 모두 안정적으로 완료되어야 합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Cold"})

        fake_check = SolutionCheckResult(
            source=workspace / "problems" / "alpha" / "solutions" / "main_solution.ac.cpp",
            expected_status="accepted",
            actual_status="accepted",
            raw_actual_status="accepted",
            run_id="cold-run",
            passed=True,
            cases=[],
            metrics={},
            status_evidence={
                "rawStatus": "accepted",
                "rankedStatus": "accepted",
                "caseStatusCounts": {},
            },
        )
        fake_pack = {
            "archivePath": str(workspace / "dist" / "packs" / "basic.aljpack"),
            "archiveLabel": "dist/packs/basic.aljpack",
            "packId": "basic",
            "platformId": "test-platform",
            "problems": ["alpha"],
            "solutionChecks": {"passed": True, "checks": []},
        }
        with (
            patch("problem_studio.web.routes.checks.compile_cases", return_value={"valid": True}),
            patch(
                "problem_studio.web.routes.checks.compile_problem_tools",
                return_value={"checker": workspace / "checker"},
            ),
            patch(
                "problem_studio.web.routes.checks.validate_all_data",
                return_value={"profileCount": 1, "caseCount": 1},
            ),
            patch(
                "problem_studio.web.routes.checks.verify_solutions",
                return_value={
                    "problemId": "alpha",
                    "profile": "hidden",
                    "passed": True,
                    "verifiedCount": 1,
                    "totalCount": 1,
                    "skippedCount": 0,
                    "checks": [fake_check.to_dict(workspace)],
                },
            ),
            patch("problem_studio.web.routes.packs.build_problem_pack", return_value=fake_pack),
        ):
            for _ in range(2):
                started = client.post("/api/problems/alpha/checks/jobs", json={"force": False})
                self.assertEqual(started.status_code, 200, started.text)
                finished = self.poll_job(client, started.json()["jobId"])
                self.assertEqual(finished["status"], "succeeded")
                self.assertEqual(finished["outcome"], "passed")

            for _ in range(2):
                started = client.post(
                    "/api/problems/alpha/packs/build",
                    json={"pack_id": "basic", "verify_profile": "hidden"},
                )
                self.assertEqual(started.status_code, 200, started.text)
                finished = self.poll_job(client, started.json()["jobId"])
                self.assertEqual(finished["status"], "succeeded")
                self.assertEqual(finished["outcome"], "passed")
                self.assertEqual(finished["progress"]["label"], "팩 생성")

    def test_problem_studio_jobs_api_lists_and_cancels_queued_job(self) -> None:
        """문제 스튜디오 작업 API 목록 조회 및 취소 대기 중 작업 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.app.state.jobs.max_running_jobs = 1
        started = threading.Event()
        release = threading.Event()

        def blocking_operation() -> dict:
            """작업 큐 취소 테스트가 실행 중 상태를 관찰할 수 있도록 이벤트가 풀릴 때까지 대기합니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
            started.set()
            release.wait(timeout=2)
            return {"ok": True}

        client.app.state.jobs.start(
            kind="blocker",
            title="blocker",
            problem_id="01",
            operation=blocking_operation,
        )
        self.assertTrue(started.wait(timeout=1))
        queued = client.post("/api/problems/01/cases/jobs", json={"profile": None})
        self.assertEqual(queued.status_code, 200, queued.text)
        queued_job = queued.json()
        self.assertEqual(queued_job["status"], "queued")

        listed = client.get("/api/jobs")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertTrue(any(job["jobId"] == queued_job["jobId"] for job in listed.json()["jobs"]))

        active_dismiss = client.delete(f"/api/jobs/{queued_job['jobId']}")
        self.assertEqual(active_dismiss.status_code, 409, active_dismiss.text)

        cancelled = client.post(f"/api/jobs/{queued_job['jobId']}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        dismissed = client.delete(f"/api/jobs/{queued_job['jobId']}")
        self.assertEqual(dismissed.status_code, 200, dismissed.text)
        release.set()

    def test_non_local_binding_blocks_workspace_and_problem_writes(self) -> None:
        """비 로컬 바인딩 차단 작업공간 및 문제 쓰기 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-remote-") as tmp:
            workspace = Path(tmp) / "workspace"
            create_problem(workspace, "alpha", "Alpha")
            client = TestClient(
                create_app(
                    workspace,
                    local_binding=False,
                    workspace_warning=True,
                    git_write_enabled=False,
                    workspace_write_enabled=False,
                )
            )

            status = client.get("/api/workspace")
            created = client.post("/api/problems", json={"problem_id": "alpha", "title": "A"})
            opened = client.post("/api/workspace/open", json={"path": str(Path(tmp) / "other")})
            linked = client.post("/api/workspace/testlib-link")
            file_write = client.put(
                "/api/problems/alpha/files/notes.md",
                json={"content": "blocked\n"},
            )
            solution_upload = client.post(
                "/api/problems/alpha/solutions/upload",
                files=[("files", ("wrong.wa.py", b"print(0)\n", "text/x-python"))],
            )
            pack_build = client.post(
                "/api/problems/alpha/packs/build",
                json={"pack_id": "alpha-pack", "verify_profile": "hidden"},
            )
            cases_job = client.post("/api/problems/alpha/cases/jobs", json={"profile": None})
            generate_job = client.post(
                "/api/problems/alpha/generate/jobs",
                json={"profile": "hidden", "force": True},
            )
            validate_job = client.post(
                "/api/problems/alpha/validate/jobs",
                json={"force": True},
            )
            tools_job = client.post(
                "/api/problems/alpha/tools/compile/jobs",
                json={"tool": "checker"},
            )
            checks_job = client.post("/api/problems/alpha/checks/jobs", json={"force": True})
            solution_job = client.post(
                "/api/problems/alpha/solutions/verify/jobs",
                json={"profile": "hidden", "solutions": None},
            )
            solution_test_job = client.post(
                "/api/problems/alpha/solutions/test/jobs",
                json={"profile": "hidden", "solution": "solutions/wrong.wa.py"},
            )
            generic_cancel = client.post("/api/jobs/missing/cancel")
            generic_dismiss = client.delete("/api/jobs/missing")
            generic_clear = client.delete("/api/jobs/completed")
            samples = client.get("/api/problems/alpha/samples")
            git_fetch = client.post("/api/workspace/git/fetch")
            problems = client.get("/api/problems")
            repositories = client.get("/api/repositories")
            problem_detail = client.get("/api/problems/alpha")
            problem_files = client.get("/api/problems/alpha/files")
            solutions = client.get("/api/problems/alpha/solutions")
            git_status = client.get("/api/workspace/git/status")
            jobs = client.get("/api/jobs")
            pack_jobs = client.get("/api/problems/alpha/packs/jobs")
            workspace_jobs = client.get("/api/workspace/packs/jobs")

        self.assertEqual(status.status_code, 403, status.text)
        self.assertEqual(created.status_code, 403, created.text)
        self.assertEqual(opened.status_code, 403, opened.text)
        self.assertEqual(linked.status_code, 403, linked.text)
        self.assertEqual(file_write.status_code, 403, file_write.text)
        self.assertEqual(solution_upload.status_code, 403, solution_upload.text)
        self.assertEqual(pack_build.status_code, 403, pack_build.text)
        self.assertEqual(cases_job.status_code, 403, cases_job.text)
        self.assertEqual(generate_job.status_code, 403, generate_job.text)
        self.assertEqual(validate_job.status_code, 403, validate_job.text)
        self.assertEqual(tools_job.status_code, 403, tools_job.text)
        self.assertEqual(checks_job.status_code, 403, checks_job.text)
        self.assertEqual(solution_job.status_code, 403, solution_job.text)
        self.assertEqual(solution_test_job.status_code, 403, solution_test_job.text)
        self.assertEqual(generic_cancel.status_code, 403, generic_cancel.text)
        self.assertEqual(generic_dismiss.status_code, 403, generic_dismiss.text)
        self.assertEqual(generic_clear.status_code, 403, generic_clear.text)
        self.assertEqual(samples.status_code, 403, samples.text)
        self.assertEqual(git_fetch.status_code, 403, git_fetch.text)
        self.assertEqual(problems.status_code, 403, problems.text)
        self.assertEqual(repositories.status_code, 403, repositories.text)
        self.assertEqual(problem_detail.status_code, 403, problem_detail.text)
        self.assertEqual(problem_files.status_code, 403, problem_files.text)
        self.assertEqual(solutions.status_code, 403, solutions.text)
        self.assertEqual(git_status.status_code, 403, git_status.text)
        self.assertEqual(jobs.status_code, 403, jobs.text)
        self.assertEqual(pack_jobs.status_code, 403, pack_jobs.text)
        self.assertEqual(workspace_jobs.status_code, 403, workspace_jobs.text)

    def test_non_local_binding_blocks_background_job_cancel_and_dismiss(self) -> None:
        """비 로컬 바인딩 차단 백그라운드 작업 취소 및 정리 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-remote-jobs-") as tmp:
            workspace = Path(tmp) / "workspace"
            create_problem(workspace, "alpha", "Alpha")
            client = TestClient(
                create_app(
                    workspace,
                    local_binding=False,
                    workspace_warning=True,
                    git_write_enabled=False,
                    workspace_write_enabled=False,
                )
            )
            release = threading.Event()
            pack_started = threading.Event()
            workspace_started = threading.Event()

            def pack_operation(cancel_token):
                """패키지 작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Args:
                    cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.

                Returns:
                    Any: 호출자가 다음 검증 단계에서 사용할 결과 값입니다.
                """
                pack_started.set()
                release.wait(5)
                return {
                    "problems": ["alpha"],
                    "archivePath": str(workspace / "dist/packs/a.aljpack"),
                }

            def workspace_operation(cancel_token):
                """작업공간 작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Args:
                    cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.

                Returns:
                    Any: 호출자가 다음 검증 단계에서 사용할 결과 값입니다.
                """
                workspace_started.set()
                release.wait(5)
                return {"problems": ["alpha"]}

            pack_job = client.app.state.jobs.start(
                kind="pack-build",
                title="pack",
                problem_id="alpha",
                operation=pack_operation,
                cancel_supported=True,
            )
            workspace_job = client.app.state.jobs.start(
                kind="workspace-pack-build",
                title="workspace",
                problem_id=WORKSPACE_JOB_PROBLEM_ID,
                operation=workspace_operation,
                cancel_supported=True,
            )
            self.assertTrue(pack_started.wait(1))
            self.assertTrue(workspace_started.wait(1))

            try:
                pack_status = client.get(f"/api/problems/alpha/packs/jobs/{pack_job.job_id}")
                pack_cancel = client.post(
                    f"/api/problems/alpha/packs/jobs/{pack_job.job_id}/cancel"
                )
                pack_dismiss = client.delete(f"/api/problems/alpha/packs/jobs/{pack_job.job_id}")
                workspace_status = client.get(f"/api/workspace/packs/jobs/{workspace_job.job_id}")
                workspace_cancel = client.post(
                    f"/api/workspace/packs/jobs/{workspace_job.job_id}/cancel"
                )
                workspace_dismiss = client.delete(
                    f"/api/workspace/packs/jobs/{workspace_job.job_id}"
                )
            finally:
                release.set()

        self.assertEqual(pack_status.status_code, 403, pack_status.text)
        self.assertEqual(workspace_status.status_code, 403, workspace_status.text)
        self.assertEqual(pack_cancel.status_code, 403, pack_cancel.text)
        self.assertEqual(pack_dismiss.status_code, 403, pack_dismiss.text)
        self.assertEqual(workspace_cancel.status_code, 403, workspace_cancel.text)
        self.assertEqual(workspace_dismiss.status_code, 403, workspace_dismiss.text)

    def test_background_job_store_dismiss_waits_until_job_is_complete(self) -> None:
        """백그라운드 작업 저장소 정리 대기 까지 작업 완료 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        jobs = BackgroundJobStore(max_jobs=5)
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        cancel_seen = {"value": False}

        def operation(cancel_token) -> dict:
            """작업 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

            Args:
                cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
            started.set()
            release.wait(timeout=2)
            cancel_seen["value"] = cancel_token.cancelled
            finished.set()
            return {"ok": True}

        job = jobs.start(
            kind="test",
            title="job",
            problem_id="01",
            operation=operation,
            cancel_supported=True,
        )
        self.assertTrue(started.wait(timeout=1))
        self.assertFalse(jobs.dismiss(job.job_id))
        self.assertIsNotNone(jobs.get(job.job_id))
        release.set()
        self.assertTrue(finished.wait(timeout=1))
        self.assertFalse(cancel_seen["value"])
        deadline = time.monotonic() + 1
        while jobs.get(job.job_id).status != "succeeded" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(jobs.dismiss(job.job_id))

    def test_workspace_can_stream_bulk_pack_build(self) -> None:
        """작업공간 가능 스트림 일괄 패키지 빌드 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """일괄 패키지 빌드 실행 문제 병렬 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-") as tmp:
            workspace = Path(tmp)
            first_started = threading.Event()
            second_started = threading.Event()

            def fake_full_test(*args, **kwargs) -> dict:
                """실제 전체 테스트 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

                Args:
                    args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                    kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

                Returns:
                    dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
                """
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
                """실제 패키지 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

                Args:
                    args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                    kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

                Returns:
                    dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
                """
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

    def test_bulk_pack_build_propagates_worker_cancellation(self) -> None:
        """일괄 패키지 빌드 전파 작업자 취소 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-") as tmp:
            workspace = Path(tmp)
            cancel_token = CancelToken()

            def fake_full_test(*args, cancel_token=None, **kwargs) -> dict:
                """실제 전체 테스트 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

                Args:
                    args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                    cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.
                    kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

                Returns:
                    dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
                """
                progress = args[4]
                cancel_token.cancel()
                progress("cancel after worker progress")
                return {
                    "problemId": args[1],
                    "passed": True,
                    "summary": "should not finish",
                }

            with (
                patch("problem_studio.core.bulk.discover_problem_ids", return_value=["01"]),
                patch(
                    "problem_studio.core.bulk.run_problem_full_test",
                    side_effect=fake_full_test,
                ),
                patch("problem_studio.core.bulk.build_problem_pack_bundle") as mocked_pack,
            ):
                with self.assertRaises(JobCancelledError):
                    build_all_problem_packs(
                        workspace,
                        "basic",
                        Path("dist/packs"),
                        max_workers=1,
                        cancel_token=cancel_token,
                    )

        mocked_pack.assert_not_called()


if __name__ == "__main__":
    unittest.main()
