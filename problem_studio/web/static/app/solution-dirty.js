/**
 * 솔루션 dirty 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { hideLastRunPanel } from "./progress.js";
import {
  clearProblemLastResult,
  currentProblemResult,
  persistProblemLastResult,
} from "./results.js";
import { roleForFile } from "./resources-view.js";
import { state } from "./state.js";
import {
  dirtySolutionSet,
  normalizedSolutionPath,
  solutionCheckSource,
  solutionValidationStatusForFile,
} from "./solution-status.js";

const dirtyCallbacks = {
  markFullTestDirty: () => {},
  renderSolutionValidationSummary: () => {},
  renderTabFiles: () => {},
  solutionFilePaths: () => [],
  updateBuildPanel: () => {},
};
export function configureSolutionDirty(callbacks = {}) {
  Object.assign(dirtyCallbacks, callbacks);
}
/**
 * dirty 솔루션 경로 값을 내부 상태나 DOM 요소에 반영합니다.
 *
 * @param {Array} paths 같은 작업을 적용할 파일 또는 디렉터리 경로 목록입니다.
 */
export function setDirtySolutionPaths(paths) {
  state.dirtySolutionPaths = Array.from(
    new Set((paths || []).map(normalizedSolutionPath).filter(Boolean))
  );
  persistProblemLastResult({ dirtySolutionPaths: state.dirtySolutionPaths });
}
/**
 * 솔루션 검사 항목을 현재 상태와 저장소에서 제거합니다.
 *
 * @param {Array} paths 같은 작업을 적용할 파일 또는 디렉터리 경로 목록입니다.
 */
export function removeSolutionChecks(paths) {
  if (!state.lastSolutionVerification?.checks?.length) return;
  const removed = new Set((paths || []).map(normalizedSolutionPath));
  if (!removed.size) return;
  state.lastSolutionVerification = {
    ...state.lastSolutionVerification,
    checks: state.lastSolutionVerification.checks.filter(
      (check) => !removed.has(normalizedSolutionPath(solutionCheckSource(check)))
    ),
  };
  persistProblemLastResult({ solutionVerification: state.lastSolutionVerification });
}
export function markSolutionDirty(path, reason = "솔루션 변경으로 재검증이 필요합니다.", options = {}) {
  const dirty = dirtySolutionSet();
  if (options.oldPath) {
    dirty.delete(normalizedSolutionPath(options.oldPath));
    removeSolutionChecks([options.oldPath]);
  }
  dirty.add(normalizedSolutionPath(path));
  setDirtySolutionPaths(Array.from(dirty));
  dirtyCallbacks.markFullTestDirty(reason);
  dirtyCallbacks.renderSolutionValidationSummary();
  dirtyCallbacks.renderTabFiles();
}
export function markAllSolutionsDirty(reason = "데이터 또는 기준 도구 변경으로 모든 솔루션 재검증이 필요합니다.") {
  setDirtySolutionPaths(dirtyCallbacks.solutionFilePaths());
  dirtyCallbacks.markFullTestDirty(reason);
  dirtyCallbacks.renderSolutionValidationSummary();
  dirtyCallbacks.renderTabFiles();
}

function fullTestStatusForFile(path) {
  const result = currentProblemResult();
  if (!result?.fullTest && !result?.dirtyAfterFullTest) return null;
  const role = roleForFile(path);
  if (result?.dirtyAfterFullTest) {
    return {
      className: "stale",
      label: "변경 후 재검증 필요",
      title: `${path} · ${role} · 변경 후 전체 테스트 필요`,
    };
  }
  if (result.fullTest?.passed) {
    return {
      className: "match",
      label: "전체 테스트 통과",
      title: `${path} · ${role} · 전체 테스트 통과`,
    };
  }
  return {
    className: "mismatch",
    label: "최근 전체 테스트 실패",
    title: `${path} · ${role} · 최근 전체 테스트 실패`,
  };
}
export function validationStatusForFile(path) {
  return solutionValidationStatusForFile(path) || fullTestStatusForFile(path);
}
/**
 * 솔루션 verification 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 */
export function clearSolutionVerification() {
  state.lastSolutionVerification = null;
  state.lastFullTest = null;
  state.lastPackResult = null;
  state.lastRun = null;
  state.dirtySolutionPaths = [];
  clearProblemLastResult();
  hideLastRunPanel();
  dirtyCallbacks.updateBuildPanel();
  dirtyCallbacks.renderSolutionValidationSummary();
  dirtyCallbacks.renderTabFiles();
}
export function discardPersistedSolutionResult() {
  state.lastSolutionVerification = null;
  state.lastFullTest = null;
  state.lastPackResult = null;
  state.lastRun = null;
  state.dirtySolutionPaths = [];
  clearProblemLastResult();
  hideLastRunPanel();
  dirtyCallbacks.updateBuildPanel();
}
