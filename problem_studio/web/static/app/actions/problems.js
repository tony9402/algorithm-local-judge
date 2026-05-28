import { api } from "../api.js";
import { clearPackJob } from "./build.js";
import { clearEditor, openFile } from "./files.js";
import { $, optional, resetWorkspaceScroll, setText } from "../dom.js";
import {
  confirmDiscardChanges,
  resetVimTransientState,
  setEditorValue,
  updateEditorVisuals,
} from "../editor/core.js";
import { resetEditorHistory } from "../editor/history.js";
import { showAlert, showResult } from "../feedback.js";
import {
  applyProblemMetadataToUi,
  currentMetadataDraft,
  currentProblemIdDraft,
  metadataFormIssues,
  metadataRawEditorDirty,
  populateMetadataForm,
  positiveIntegerInput,
  renderMetadataValidation,
  textInputValue,
} from "../metadata-view.js";
import { hideLastRunPanel, renderLastRunPanel } from "../progress.js";
import {
  clearProblemLastResult,
  currentProblemResult,
  migrateProblemLastResult,
  persistProblemLastResult,
} from "../results.js";
import {
  filesForTab,
  renderTabFiles,
  selectSolutionPath,
} from "../resources-view.js";
import { DELETE_CONFIRM_PHRASE, state } from "../state.js";
import { renderTaskPanel } from "../tabs-view.js";
import {
  rememberSelectedFile,
  rememberView,
  restoreViewPreference,
  selectionKey,
} from "../view-persistence.js";
import {
  problemLabel,
  renderProblems,
  renderWorkspace,
} from "../workspace-view.js";
import { normalizedSolutionPath } from "../solution-status.js";
import { updateBuildPanel } from "../build-view.js";
import { refreshGitStatus } from "./git.js";

const problemCallbacks = {
  closeModals: () => {},
  isCurrentView: (seq) => seq === state.viewSeq,
  nextViewSeq: () => {
    state.viewSeq += 1;
    return state.viewSeq;
  },
  openModal: () => {},
};

export function configureProblemActions(callbacks = {}) {
  Object.assign(problemCallbacks, callbacks);
}

function migrateTabSelections(previousProblemId, nextProblemId) {
  if (!previousProblemId || !nextProblemId || previousProblemId === nextProblemId) return;
  const migrated = {};
  for (const [key, value] of Object.entries(state.tabSelections || {})) {
    const prefix = `${previousProblemId}:`;
    migrated[key.startsWith(prefix) ? `${nextProblemId}:${key.slice(prefix.length)}` : key] = value;
  }
  state.tabSelections = migrated;
}

function applyProblemRenameResult(result, previousProblemId) {
  const nextProblemId = result.problemId;
  if (!nextProblemId || nextProblemId === previousProblemId) return;
  migrateProblemLastResult(previousProblemId, nextProblemId);
  migrateTabSelections(previousProblemId, nextProblemId);
  if (state.activePackJob?.problemId === previousProblemId) clearPackJob();
  state.selectedProblem = nextProblemId;
  if (state.detail) {
    state.detail = {
      ...state.detail,
      problemId: nextProblemId,
      path: result.path || state.detail.path,
      metadata: result.metadata || state.detail.metadata,
    };
  }
  if (result.workspace) {
    renderWorkspace(result.workspace);
    renderProblems(result.workspace.problems || []);
  }
  rememberView();
}

export function restoreProblemLastResult(problemId = state.selectedProblem) {
  const result = currentProblemResult(problemId);
  state.lastSolutionVerification = result?.solutionVerification || null;
  state.lastFullTest = result?.fullTest || null;
  state.lastPackResult = result?.lastPackResult || null;
  state.lastRun = result?.lastRun || null;
  state.dirtySolutionPaths = Array.isArray(result?.dirtySolutionPaths)
    ? result.dirtySolutionPaths.map(normalizedSolutionPath)
    : [];
  renderLastRunPanel();
  updateBuildPanel();
}

export function markFullTestDirty(reason = "변경사항이 저장되어 전체 테스트가 필요합니다.") {
  if (!state.selectedProblem) return;
  const current = currentProblemResult() || {};
  persistProblemLastResult({
    ...current,
    dirtyAfterFullTest: true,
    dirtyReason: reason,
    lastPackResult: null,
  });
  state.lastFullTest = current.fullTest || null;
  state.lastPackResult = null;
  updateBuildPanel();
  renderTabFiles();
}

export async function refresh() {
  const seq = problemCallbacks.nextViewSeq();
  const workspace = await api("/api/workspace");
  if (!problemCallbacks.isCurrentView(seq)) return;
  state.activeRepository = workspace.activeRepository || null;
  state.repositoryMode = Boolean(workspace.repositoryMode);
  state.repositories = workspace.repositories || [];
  const preferred = restoreViewPreference(workspace.problems || []);
  renderWorkspace(workspace);
  await refreshGitStatus();
  renderProblems(workspace.problems || []);
  const selectedStillExists = workspace.problems?.some(
    (problem) => problem.problemId === state.selectedProblem
  );
  if (selectedStillExists) {
    await selectProblem(state.selectedProblem, seq);
  } else if (preferred.problemId) {
    state.selectedTab = preferred.tabId;
    await selectProblem(preferred.problemId, seq);
  } else if (workspace.problems?.length) {
    await selectProblem(workspace.problems[0].problemId, seq);
  } else {
    state.selectedProblem = null;
    state.detail = null;
    state.files = [];
    state.lastSolutionVerification = null;
    state.lastRun = null;
    hideLastRunPanel();
    renderTaskPanel();
    clearEditor();
  }
}

export async function selectProblem(problemId, seq = problemCallbacks.nextViewSeq()) {
  const switchedProblem = state.selectedProblem !== problemId;
  if (switchedProblem && !confirmDiscardChanges()) return;
  rememberSelectedFile();
  state.selectedProblem = problemId;
  const detail = await api(`/api/problems/${encodeURIComponent(problemId)}`);
  if (!problemCallbacks.isCurrentView(seq)) return;
  state.detail = detail;
  state.files = detail.files || [];
  if (switchedProblem) {
    state.selectedFile = null;
    setEditorValue("", { clearHistory: true });
    state.lastSavedContent = "";
    resetEditorHistory();
    resetVimTransientState();
    updateEditorVisuals();
  }
  restoreProblemLastResult(problemId);
  applyProblemMetadataToUi(detail.metadata);
  populateMetadataForm(detail.metadata);
  rememberView();
  await selectTab(state.selectedTab, seq);
}

export async function selectTab(tabId, seq = problemCallbacks.nextViewSeq()) {
  if (tabId !== state.selectedTab && !confirmDiscardChanges()) return;
  rememberSelectedFile();
  state.selectedTab = tabId;
  rememberView();
  renderTaskPanel();
  resetWorkspaceScroll();
  const files = filesForTab(tabId);
  const rememberedPath = state.tabSelections[selectionKey(state.selectedProblem, tabId)];
  const remembered = files.find((file) => file.path === rememberedPath);
  const currentStillVisible = files.some((file) => file.path === state.selectedFile);
  if (tabId === "solutions") {
    const selected = remembered || (currentStillVisible ? files.find((file) => file.path === state.selectedFile) : null) || files[0];
    clearEditor("솔루션 소스 편집은 각 솔루션의 소스 편집 버튼에서 진행합니다.");
    if (selected) selectSolutionPath(selected.path);
    else renderTabFiles();
    return;
  }
  if (files.length && remembered) {
    await openFile(remembered.path, false, seq, true);
  } else if (files.length && !currentStillVisible) {
    await openFile(files[0].path, false, seq, true);
  } else if (!files.length) {
    clearEditor("이 탭에서 작업할 파일이 없습니다.");
  } else {
    renderTabFiles();
  }
}

export async function saveMetadata() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  if (metadataRawEditorDirty()) {
    throw new Error("원본 problem.json 편집 내용이 저장되지 않았습니다. 원본을 저장하거나 되돌린 뒤 폼을 저장하세요.");
  }
  const issues = metadataFormIssues();
  if (issues.length) {
    renderMetadataValidation();
    throw new Error(`문제 정보 저장 전에 확인하세요.\n${issues.join("\n")}`);
  }
  const metadata = currentMetadataDraft();
  const previousProblemId = state.selectedProblem;
  const nextProblemId = currentProblemIdDraft();
  if (nextProblemId !== previousProblemId) {
    const renameResult = await api(`/api/problems/${encodeURIComponent(previousProblemId)}/id`, {
      method: "PATCH",
      body: JSON.stringify({ problem_id: nextProblemId }),
    });
    applyProblemRenameResult(renameResult, previousProblemId);
  }
  const result = await api(`/api/problems/${encodeURIComponent(state.selectedProblem)}/metadata`, {
    method: "PATCH",
    body: JSON.stringify({ metadata }),
  });
  applyProblemMetadataToUi(result, { markDirty: true });
  showResult(
    nextProblemId !== previousProblemId
      ? `${previousProblemId} 문제 번호를 ${nextProblemId}로 변경했습니다.`
      : "문제 정보가 저장되었습니다.",
    "summary success"
  );
  if (state.selectedFile === "problem.json") await openFile("problem.json", true);
}

export async function createProblem() {
  const problemId = $("newProblemId").value.trim();
  const title = $("newProblemTitle").value.trim() || "Untitled Problem";
  const folder = $("newProblemFolder").value.trim();
  const version = positiveIntegerInput("newProblemVersion", 1);
  const defaultProfile = textInputValue("newProblemDefaultProfile", "hidden");
  const limits = {
    compileTimeoutMs: positiveIntegerInput("newProblemCompileTimeout", 5000),
    generationTimeoutMs: positiveIntegerInput("newProblemGenerationTimeout", 5000),
    solutionTimeoutMs: positiveIntegerInput("newProblemSolutionTimeout", 2000),
    userTimeoutMs: positiveIntegerInput("newProblemUserTimeout", 2000),
  };
  await api("/api/problems", {
    method: "POST",
    body: JSON.stringify({
      problem_id: problemId,
      title,
      folder,
      version,
      default_profile: defaultProfile,
      limits,
    }),
  });
  problemCallbacks.closeModals();
  await refresh();
  await selectProblem(problemId);
  showResult(`Created problem ${problemId}`, "summary success");
}

export function updateDeleteProblemButton() {
  const input = optional("deleteProblemConfirmInput");
  const button = optional("deleteProblemButton");
  if (!button) return;
  button.disabled = (
    !state.selectedProblem
    || input?.value !== DELETE_CONFIRM_PHRASE
    || document.body.getAttribute("aria-busy") === "true"
  );
}

export function openDeleteProblemModal() {
  if (!state.selectedProblem) throw new Error("삭제할 문제를 먼저 선택하세요.");
  const problem = state.problems.find((item) => item.problemId === state.selectedProblem);
  const label = problem ? problemLabel(problem) : state.selectedProblem;
  setText("deleteProblemDescription", `${label} 문제를 삭제합니다.`);
  $("deleteProblemConfirmInput").value = "";
  updateDeleteProblemButton();
  problemCallbacks.openModal("deleteProblemModal");
}

export async function deleteSelectedProblem() {
  if (!state.selectedProblem) throw new Error("삭제할 문제를 먼저 선택하세요.");
  const problemId = state.selectedProblem;
  const confirmPhrase = $("deleteProblemConfirmInput").value;
  if (confirmPhrase !== DELETE_CONFIRM_PHRASE) {
    throw new Error(`삭제하려면 "${DELETE_CONFIRM_PHRASE}"를 정확히 입력하세요.`);
  }
  await api(`/api/problems/${encodeURIComponent(problemId)}`, {
    method: "DELETE",
    body: JSON.stringify({ confirm_phrase: confirmPhrase }),
  });
  clearProblemLastResult(problemId);
  if (state.activePackJob?.problemId === problemId) clearPackJob();
  state.selectedProblem = null;
  state.selectedFile = null;
  state.detail = null;
  state.files = [];
  problemCallbacks.closeModals();
  await refresh();
  showAlert(`${problemId} 문제를 삭제했습니다.`, "success", {
    title: "문제 삭제 완료",
    timeout: 5000,
  });
}
