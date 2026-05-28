import { PERSISTED_VIEW_KEY, TAB_CONFIGS, activeRepositoryKey, state } from "./state.js";
import { readStorage, writeStorage } from "./storage.js";

/**
 * selectionKey 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} problemId `problemId` 값입니다.
 * @param {any} tabId `tabId` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function selectionKey(problemId = state.selectedProblem, tabId = state.selectedTab) {
  return `${activeRepositoryKey()}:${problemId || "-"}:${tabId || "-"}`;
}

/**
 * persistedView 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function persistedView() {
  const view = readStorage(PERSISTED_VIEW_KEY);
  return view && typeof view === "object" ? view : {};
}

/**
 * rememberView 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function rememberView() {
  const previous = persistedView();
  writeStorage(PERSISTED_VIEW_KEY, {
    ...previous,
    repositoryName: state.activeRepository || null,
    problemId: state.selectedProblem || previous.problemId || null,
    tabId: state.selectedTab,
    filePath: state.selectedFile,
    tabSelections: state.tabSelections,
    problemFolderCollapsed: state.problemFolderCollapsed,
  });
}

/**
 * restoreViewPreference 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} problems `problems` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function restoreViewPreference(problems) {
  const view = persistedView();
  /**
   * sameRepository 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} view `view` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  const sameRepository = (view.repositoryName || null) === (state.activeRepository || null);
  if (view.problemFolderCollapsed && typeof view.problemFolderCollapsed === "object") {
    state.problemFolderCollapsed = Object.fromEntries(
      Object.entries(view.problemFolderCollapsed).filter(([, collapsed]) => collapsed === true)
    );
  }
  if (view.tabSelections && typeof view.tabSelections === "object") {
    state.tabSelections = { ...state.tabSelections, ...view.tabSelections };
  }
  if (sameRepository && view.problemId && view.tabId && view.filePath) {
    state.tabSelections[selectionKey(view.problemId, view.tabId)] = view.filePath;
  }
  const problemIds = new Set((problems || []).map((problem) => problem.problemId));
  const preferredProblem = sameRepository && problemIds.has(view.problemId) ? view.problemId : null;
  const preferredTab = sameRepository && TAB_CONFIGS[view.tabId] ? view.tabId : "info";
  return { problemId: preferredProblem, tabId: preferredTab };
}

/**
 * rememberSelectedFile 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function rememberSelectedFile() {
  if (!state.selectedProblem || !state.selectedTab || !state.selectedFile) return;
  state.tabSelections[selectionKey()] = state.selectedFile;
  rememberView();
}
