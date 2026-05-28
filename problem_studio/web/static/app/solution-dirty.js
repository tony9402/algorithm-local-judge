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
  /**
   * markFullTestDirty 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  markFullTestDirty: () => {},
  /**
   * renderSolutionValidationSummary 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renderSolutionValidationSummary: () => {},
  /**
   * renderTabFiles 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renderTabFiles: () => {},
  /**
   * solutionFilePaths 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  solutionFilePaths: () => [],
  /**
   * updateBuildPanel 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateBuildPanel: () => {},
};

/**
 * configureSolutionDirty 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureSolutionDirty(callbacks = {}) {
  Object.assign(dirtyCallbacks, callbacks);
}

/**
 * setDirtySolutionPaths 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} paths 경로 목록입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function setDirtySolutionPaths(paths) {
  state.dirtySolutionPaths = Array.from(
    new Set((paths || []).map(normalizedSolutionPath).filter(Boolean))
  );
  persistProblemLastResult({ dirtySolutionPaths: state.dirtySolutionPaths });
}

/**
 * removeSolutionChecks 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} paths 경로 목록입니다.
 * @returns {any} 처리 결과를 반환합니다.
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

/**
 * markSolutionDirty 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @param {any} reason `reason` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * markAllSolutionsDirty 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} reason `reason` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function markAllSolutionsDirty(reason = "데이터 또는 기준 도구 변경으로 모든 솔루션 재검증이 필요합니다.") {
  setDirtySolutionPaths(dirtyCallbacks.solutionFilePaths());
  dirtyCallbacks.markFullTestDirty(reason);
  dirtyCallbacks.renderSolutionValidationSummary();
  dirtyCallbacks.renderTabFiles();
}

/**
 * fullTestStatusForFile 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * validationStatusForFile 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function validationStatusForFile(path) {
  return solutionValidationStatusForFile(path) || fullTestStatusForFile(path);
}

/**
 * clearSolutionVerification 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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

/**
 * discardPersistedSolutionResult 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
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
