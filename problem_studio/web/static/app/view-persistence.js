/**
 * 화면 persistence 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { PERSISTED_VIEW_KEY, TAB_CONFIGS, activeRepositoryKey, state } from "./state.js";
import { readStorage, writeStorage } from "./storage.js";
export function selectionKey(problemId = state.selectedProblem, tabId = state.selectedTab) {
  return `${activeRepositoryKey()}:${problemId || "-"}:${tabId || "-"}`;
}
export function persistedView() {
  const view = readStorage(PERSISTED_VIEW_KEY);
  return view && typeof view === "object" ? view : {};
}
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
export function restoreViewPreference(problems) {
  const view = persistedView();
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
export function rememberSelectedFile() {
  if (!state.selectedProblem || !state.selectedTab || !state.selectedFile) return;
  state.tabSelections[selectionKey()] = state.selectedFile;
  rememberView();
}
