import {
  configureFileActions,
  openFile,
  saveFile,
  saveOpenFileIfDirty,
} from "./app/actions/files.js";
import {
  configureSolutionActions,
  createSolution,
  deleteSolution,
  openSolutionStressModal,
  openStressMismatchModal,
  openSolutionCasesModal,
  openSolutionCreateModal,
  openSolutionEditModal,
  openSolutionUpload,
  renameSolution,
  renderSolutionMetaForm,
  solutionFilePaths,
  runSolutionStress,
  updateSolutionStressScope,
  updateSolutionPreview,
  updateSolutionRenamePreview,
  uploadSolutions,
  verifySingleSolution,
  verifySolutions,
} from "./app/actions/solutions.js";
import {
  compileCases,
  compileTool,
  generateData,
  streamRequest,
  validateAllData,
} from "./app/actions/data.js";
import {
  buildAllPacksOnce,
  buildPack,
  cancelActiveBulkJob,
  cancelActivePackJob,
  configureBuildActions,
  dismissStalePackJob,
  formatTime,
  openWorkspaceBuildModal,
  packJobSummary,
  runAllChecksOnce,
  selectedBulkProblemIdsFromModal,
  syncPackJobFromStorage,
  updateBulkStartButton,
  updateGlobalActionState,
} from "./app/actions/build.js";
import {
  configureProblemActions,
  createProblem,
  deleteSelectedProblem,
  markFullTestDirty,
  openDeleteProblemModal,
  refresh,
  restoreProblemLastResult,
  saveMetadata,
  selectProblem,
  selectTab,
  updateDeleteProblemButton,
} from "./app/actions/problems.js";
import {
  enqueueValidationAction,
  VALIDATION_QUEUE_ACTIONS,
} from "./app/actions/validation-queue.js";
import {
  commitGitChanges,
  configureGitActions,
  runGitAction,
} from "./app/actions/git.js?v=20260712-01";
import {
  bindGitDrawer,
  closeGitDrawer,
  configureGitView,
  isGitDrawerOpen,
} from "./app/git-view.js?v=20260712-01";
import {
  cloneRepositoryFromModal,
  configureRepositoryActions,
  moveFromRepositoryOpenToClone,
  openSelectedRepositoryFromModal,
  openRepositoryModal,
  refreshRepositoryOpenList,
  refreshRepositories,
  renderRepositoryOpenOptions,
  selectRepository,
  updateRepositoryClonePreview,
} from "./app/actions/repositories.js";
import {
  configureBuildView,
  updateBuildDashboard,
  updateBuildPanel,
} from "./app/build-view.js";
import { bindAppEvents } from "./app/events.js";
import { configureLoading, withErrors, withInlineErrors } from "./app/loading.js";
import { activeModalId, closeModalSurface, closeModals, openModal } from "./app/modal.js";
import {
  focusEditor,
  currentSolutionModalDraft,
  getEditorValue,
  initializeCodeMirror,
  initializeSourceModalEditors,
  modalEditorKeyForElement,
  restoreSolutionModalDraft,
  setEditorValue,
} from "./app/editor/codemirror.js";
import {
  bindEditorEvents,
  closeEditorCommandLine,
  configureEditorCore,
  confirmDiscardChanges,
  hasUnsavedChanges,
  restoreEditorSettings,
  setEditorMode,
  setEditorSettingsOpen,
  submitEditorCommandLine,
  updateDirtyState,
} from "./app/editor/core.js";
import { showAlert, showResult } from "./app/feedback.js";
import {
  bindJobCenter,
  closeJobCenter,
  configureJobsView,
  isJobCenterOpen,
} from "./app/jobs-view.js";
import {
  configureMetadataView,
  currentMetadataFormDraft,
  populateMetadataForm,
  restoreMetadataFormDraft,
  updateMetadataPreview,
} from "./app/metadata-view.js";
import {
  bindUnsavedChangesModal,
  cancelUnsavedPrompt,
  clearSolutionModalSnapshot,
  configureUnsavedChanges,
  guardUnsavedTransition,
  hasAnyUnsavedChanges,
  requestCloseSurface,
} from "./app/unsaved-changes.js";
import {
  completeProgress,
  hideLastRunPanel,
  renderLastRunPanel,
  renderProgressPanel,
} from "./app/progress.js";
import {
  configureResourcesView,
  filesForTab,
  isReferenceSolutionPath,
  renderSolutionValidationSummary,
  renderTabFiles,
  selectSolutionPath,
} from "./app/resources-view.js";
import { SAVE_BEFORE_ACTIONS, TAB_CONFIGS, state } from "./app/state.js";
import { persistProblemLastResult } from "./app/results.js";
import {
  configureSolutionDirty,
  markAllSolutionsDirty,
  markSolutionDirty,
  removeSolutionChecks,
  setDirtySolutionPaths,
  validationStatusForFile,
} from "./app/solution-dirty.js";
import {
  configureTabsView,
  currentPrimaryAction,
  renderTaskPanel,
} from "./app/tabs-view.js";
import {
  closeSidebar,
  configureWorkspaceView,
  folderLabel,
  renderProblems,
  renderWorkspace,
  setProblemFilter,
  syncSidebarAccessibility,
  syncWorkspaceProblemSummaries,
  toggleSidebar,
  updateMobileHeader,
} from "./app/workspace-view.js";

configureEditorCore({
  createSolution,
  currentPrimaryAction,
  renameSolution,
  runTabAction,
  saveFile,
  withErrors,
});
configureResourcesView({
  deleteSolution,
  openFile,
  openSolutionCasesModal,
  openSolutionEditModal,
  openSolutionStressModal,
  openStressMismatchModal,
  validationStatusForFile,
  verifySingleSolution,
  withErrors,
});
configureTabsView({
  openSolutionUpload,
  populateMetadataForm,
  renderLastRunPanel,
  renderSolutionMetaForm,
  renderSolutionValidationSummary,
  renderTabFiles,
  runTabAction,
  showAlert,
  updateBuildPanel,
  updateGlobalActionState,
  withErrors,
  withInlineErrors,
});
configureMetadataView({
  folderLabel,
  hasUnsavedChanges,
  markFullTestDirty,
  renderProblems,
  syncWorkspaceProblemSummaries,
  updateMobileHeader,
});
configureWorkspaceView({
  closeGitDrawer,
  closeJobCenter,
  selectProblem,
  withErrors,
});

function failureSourcePath(detail, problemId) {
  const raw = String(detail.source || detail.path || detail.sourcePath || "").replaceAll("\\", "/");
  const prefix = problemId ? `problems/${problemId}/` : "";
  if (prefix && raw.startsWith(prefix)) return raw.slice(prefix.length);
  const problemMarker = raw.indexOf("/problems/");
  if (problemMarker >= 0 && problemId) {
    const nestedPrefix = `/problems/${problemId}/`;
    const nestedIndex = raw.indexOf(nestedPrefix, problemMarker);
    if (nestedIndex >= 0) return raw.slice(nestedIndex + nestedPrefix.length);
  }
  return raw;
}

function tabForFailurePath(path) {
  if (path.startsWith("solutions/")) return "solutions";
  for (const tabId of Object.keys(TAB_CONFIGS)) {
    if (filesForTab(tabId).some((file) => file.path === path)) return tabId;
  }
  return state.selectedTab;
}

async function openFailureTarget(detail, action, job) {
  const problemId = detail.problemId || job.problemId || job.target?.problemId || null;
  if (problemId && problemId !== state.selectedProblem) await selectProblem(problemId);
  if (problemId && state.selectedProblem !== problemId) return;
  const path = failureSourcePath(detail, problemId || state.selectedProblem);
  if (!path) throw new Error("열 수 있는 실패 대상 파일이 없습니다.");
  const tabId = tabForFailurePath(path);
  await selectTab(tabId);
  if (state.selectedTab !== tabId) return;
  closeJobCenter({ restoreFocus: false });
  if (path.startsWith("solutions/")) {
    selectSolutionPath(path);
    if (action === "artifact") openSolutionCasesModal(path);
    else if (action === "file") await openSolutionEditModal(path);
    else document.querySelector(`[data-solution-path="${CSS.escape(path)}"]`)?.scrollIntoView({ block: "nearest" });
  } else {
    await openFile(path, false);
  }
  if (action === "solution") {
    document.querySelector(`[data-solution-path="${CSS.escape(path)}"] .solution-row-main`)?.focus();
  }
}

configureJobsView({
  closeGitDrawer,
  closeSidebar,
  openFailureTarget: (detail, action, job) => withErrors(
    () => openFailureTarget(detail, action, job),
    "실패한 작업 대상을 여는 중입니다."
  ),
});
configureGitView({
  closeJobCenter,
  closeSidebar,
});
configureBuildView({
  formatTime,
  packJobSummary,
});
configureBuildActions({
  openModal,
  restoreProblemLastResult,
});
configureLoading({
  completeProgress,
  renderProgressPanel,
});
configureSolutionDirty({
  markFullTestDirty,
  renderSolutionValidationSummary,
  renderTabFiles,
  solutionFilePaths,
  updateBuildPanel,
});
configureProblemActions({
  closeModals,
  closeJobCenter,
  isCurrentView,
  nextViewSeq,
  openModal,
});
configureFileActions({
  confirmDiscardChanges,
  hasUnsavedChanges,
  isCurrentView,
  isReferenceSolutionPath,
  markAllSolutionsDirty,
  markFullTestDirty,
  markSolutionDirty,
  nextViewSeq,
  renderSolutionMetaForm,
  renderSolutionValidationSummary,
  renderTabFiles,
  setDirtySolutionPaths,
  showResult,
  solutionFilePaths,
});
configureSolutionActions({
  closeModals,
  markFullTestDirty,
  markSolutionDirty,
  openModal,
  persistProblemLastResult,
  removeSolutionChecks,
  renderTaskPanel,
  setDirtySolutionPaths,
  streamRequest,
  withErrors,
  withInlineErrors,
});
configureGitActions({
  refresh: () => refresh({ skipGuard: true }),
  renderProblems,
  renderWorkspace,
});
configureRepositoryActions({
  closeModals,
  openModal,
  refresh: () => refresh({ skipGuard: true }),
  syncPackJobFromStorage,
});

configureUnsavedChanges({
  currentFileContent: getEditorValue,
  currentMetadataDraft: currentMetadataFormDraft,
  currentSolutionModalDraft,
  discardFile: (savedContent) => {
    setEditorValue(savedContent, { clearHistory: true });
    updateDirtyState();
  },
  discardMetadata: (savedCanonicalDraft) => {
    const draft = JSON.parse(savedCanonicalDraft || "{}");
    restoreMetadataFormDraft(draft);
  },
  discardSolutionModal: (savedCanonicalDraft) => {
    const draft = JSON.parse(savedCanonicalDraft || "{}");
    restoreSolutionModalDraft(draft);
    if (draft.mode === "create") updateSolutionPreview();
    else updateSolutionRenamePreview();
  },
  forceCloseSurface: (surfaceId) => {
    const closed = closeModalSurface(surfaceId);
    if (["solutionCreateModal", "solutionEditModal"].includes(surfaceId)) {
      clearSolutionModalSnapshot();
    }
    return closed;
  },
  saveFile,
  saveMetadata,
  saveSolutionModal: () => state.unsaved.solutionModal.mode === "create"
    ? createSolution()
    : renameSolution(),
});

const ACTIONS = {
  saveMetadata: () => saveMetadata(),
  openDeleteProblem: () => openDeleteProblemModal(),
  compileCases: () => compileCases(),
  compileGenerator: () => compileTool("generator", "Generator"),
  generateSample: () => generateData("sample"),
  generateHidden: () => generateData("hidden"),
  compileValidator: () => compileTool("validator", "Validator"),
  validateSample: () => validateAllData(),
  compileChecker: () => compileTool("checker", "Checker"),
  compileReference: () => compileTool("solution", "Reference solution"),
  compileTools: () => compileTools(),
  newSolution: () => openSolutionCreateModal(),
  uploadSolutions: () => openSolutionUpload(),
  verifySolutions: () => verifySolutions(),
  stressSolutions: () => openSolutionStressModal(),
  runAllChecks: () => runAllChecksOnce(),
  buildPack: () => buildPack(),
  buildAllPacks: () => buildAllPacksOnce(),
};

if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";

function nextViewSeq() {
  state.viewSeq += 1;
  return state.viewSeq;
}

function isCurrentView(seq) {
  return seq === state.viewSeq;
}

async function runTabAction(actionId) {
  const run = async () => {
    if (SAVE_BEFORE_ACTIONS.has(actionId)) await saveOpenFileIfDirty();
    return ACTIONS[actionId]();
  };
  if (VALIDATION_QUEUE_ACTIONS.has(actionId)) {
    const action = Object.values(TAB_CONFIGS)
      .flatMap((config) => config.actions)
      .find((item) => item.id === actionId);
    return enqueueValidationAction(action?.label || "검증", run);
  }
  return run();
}

initializeCodeMirror();
initializeSourceModalEditors();
bindUnsavedChangesModal();
bindGitDrawer();
bindJobCenter();
bindAppEvents({
  bindEditorEvents,
  buildAllPacksOnce,
  buildPack,
  cancelActiveBulkJob,
  cancelActivePackJob,
  closeEditorCommandLine,
  closeGitDrawer,
  closeJobCenter,
  closeModals,
  closeSidebar,
  commitGitChanges,
  cloneRepositoryFromModal,
  createProblem,
  createSolution,
  deleteSelectedProblem,
  dismissStalePackJob,
  focusEditor,
  activeModalId,
  cancelUnsavedPrompt,
  guardUnsavedTransition,
  hasAnyUnsavedChanges,
  hasUnsavedChanges,
  hideLastRunPanel,
  isGitDrawerOpen,
  isJobCenterOpen,
  modalEditorKeyForElement,
  openModal,
  openRepositoryModal,
  openSelectedRepositoryFromModal,
  refreshRepositories,
  refreshRepositoryOpenList,
  renderRepositoryOpenOptions,
  moveFromRepositoryOpenToClone,
  openWorkspaceBuildModal,
  renameSolution,
  renderTabFiles,
  renderTaskPanel,
  requestCloseSurface,
  restoreProblemLastResult,
  runAllChecksOnce,
  runSolutionStress,
  runGitAction,
  saveFile,
  selectTab,
  setProblemFilter,
  selectRepository,
  selectedBulkProblemIdsFromModal,
  setEditorMode,
  setEditorSettingsOpen,
  submitEditorCommandLine,
  syncPackJobFromStorage,
  toggleSidebar,
  updateBuildDashboard,
  updateBulkStartButton,
  updateDeleteProblemButton,
  updateGlobalActionState,
  updateMetadataPreview,
  updateRepositoryClonePreview,
  updateSolutionStressScope,
  updateSolutionPreview,
  updateSolutionRenamePreview,
  uploadSolutions,
  withErrors,
  withInlineErrors,
});
syncSidebarAccessibility();
window.addEventListener("resize", syncSidebarAccessibility);
restoreEditorSettings();
updateSolutionPreview();
syncPackJobFromStorage();
updateGlobalActionState();
withErrors(refresh, "워크스페이스를 불러오는 중입니다.");
