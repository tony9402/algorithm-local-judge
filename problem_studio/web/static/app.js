import {
  configureFileActions,
  openFile,
  saveFile,
  saveOpenFileIfDirty,
} from "./app/actions/files.js";
import {
  configureSolutionActions,
  createSolution,
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
} from "./app/actions/git.js?v=20260522-01";
import {
  cloneRepositoryFromModal,
  configureRepositoryActions,
  openRepositoryModal,
  refreshRepositories,
  registerRepositoryFromModal,
  selectRepository,
} from "./app/actions/repositories.js";
import {
  configureBuildView,
  updateBuildDashboard,
  updateBuildPanel,
} from "./app/build-view.js";
import { bindAppEvents } from "./app/events.js";
import { configureLoading, withErrors, withInlineErrors } from "./app/loading.js";
import { closeModals, openModal } from "./app/modal.js";
import {
  focusEditor,
  initializeCodeMirror,
  initializeSourceModalEditors,
  modalEditorKeyForElement,
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
} from "./app/editor/core.js";
import { showAlert, showResult } from "./app/feedback.js";
import { bindJobCenter } from "./app/jobs-view.js";
import { configureMetadataView, populateMetadataForm, updateMetadataPreview } from "./app/metadata-view.js";
import {
  completeProgress,
  hideLastRunPanel,
  renderLastRunPanel,
  renderProgressPanel,
} from "./app/progress.js";
import {
  configureResourcesView,
  isReferenceSolutionPath,
  renderSolutionValidationSummary,
  renderTabFiles,
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
  selectProblem,
  withErrors,
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
  updateDeleteProblemButton,
  updateGlobalActionState,
  updateSolutionPreview,
  updateSolutionRenamePreview,
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
  refresh,
  renderProblems,
  renderWorkspace,
});
configureRepositoryActions({
  closeModals,
  confirmDiscardChanges,
  refresh,
  syncPackJobFromStorage,
});

const ACTIONS = {
  /**
   * saveMetadata 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  saveMetadata: () => saveMetadata(),
  /**
   * openDeleteProblem 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  openDeleteProblem: () => openDeleteProblemModal(),
  /**
   * compileCases 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  compileCases: () => compileCases(),
  /**
   * compileGenerator 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  compileGenerator: () => compileTool("generator", "Generator"),
  /**
   * generateSample 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  generateSample: () => generateData("sample"),
  /**
   * generateHidden 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  generateHidden: () => generateData("hidden"),
  /**
   * compileValidator 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  compileValidator: () => compileTool("validator", "Validator"),
  /**
   * validateSample 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  validateSample: () => validateAllData(),
  /**
   * compileChecker 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  compileChecker: () => compileTool("checker", "Checker"),
  /**
   * compileReference 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  compileReference: () => compileTool("solution", "Reference solution"),
  /**
   * compileTools 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  compileTools: () => compileTools(),
  /**
   * newSolution 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  newSolution: () => openSolutionCreateModal(),
  /**
   * uploadSolutions 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  uploadSolutions: () => openSolutionUpload(),
  /**
   * verifySolutions 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  verifySolutions: () => verifySolutions(),
  /**
   * stressSolutions 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  stressSolutions: () => openSolutionStressModal(),
  /**
   * runAllChecks 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  runAllChecks: () => runAllChecksOnce(),
  /**
   * buildPack 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  buildPack: () => buildPack(),
  /**
   * buildAllPacks 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  buildAllPacks: () => buildAllPacksOnce(),
};

if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";

/**
 * nextViewSeq 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function nextViewSeq() {
  state.viewSeq += 1;
  return state.viewSeq;
}

/**
 * isCurrentView 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} seq `seq` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function isCurrentView(seq) {
  return seq === state.viewSeq;
}

/**
 * runTabAction 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} actionId `actionId` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function runTabAction(actionId) {
  /**
   * run 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
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
bindJobCenter();
bindAppEvents({
  bindEditorEvents,
  buildAllPacksOnce,
  buildPack,
  cancelActiveBulkJob,
  cancelActivePackJob,
  closeEditorCommandLine,
  closeModals,
  closeSidebar,
  commitGitChanges,
  cloneRepositoryFromModal,
  createProblem,
  createSolution,
  deleteSelectedProblem,
  dismissStalePackJob,
  focusEditor,
  hasUnsavedChanges,
  hideLastRunPanel,
  modalEditorKeyForElement,
  openModal,
  openRepositoryModal,
  refreshRepositories,
  registerRepositoryFromModal,
  openWorkspaceBuildModal,
  renameSolution,
  renderTabFiles,
  renderTaskPanel,
  restoreProblemLastResult,
  runAllChecksOnce,
  runSolutionStress,
  runGitAction,
  saveFile,
  selectTab,
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
  updateSolutionStressScope,
  updateSolutionPreview,
  updateSolutionRenamePreview,
  uploadSolutions,
  withErrors,
  withInlineErrors,
});
restoreEditorSettings();
updateSolutionPreview();
syncPackJobFromStorage();
updateGlobalActionState();
withErrors(refresh, "워크스페이스를 불러오는 중입니다.");
