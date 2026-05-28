import { $, setText } from "./dom.js";
import { showAlert } from "./feedback.js";
import { state } from "./state.js";

const loadingCallbacks = {
  /**
   * completeProgress 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  completeProgress: () => {},
  /**
   * renderProgressPanel 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renderProgressPanel: () => {},
  /**
   * updateDeleteProblemButton 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateDeleteProblemButton: () => {},
  /**
   * updateGlobalActionState 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateGlobalActionState: () => {},
  /**
   * updateSolutionPreview 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateSolutionPreview: () => {},
  /**
   * updateSolutionRenamePreview 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateSolutionRenamePreview: () => {},
};

/**
 * configureLoading 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureLoading(callbacks = {}) {
  Object.assign(loadingCallbacks, callbacks);
}

/**
 * setControlsDisabled 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} disabled `disabled` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function setControlsDisabled(disabled) {
  document.body.setAttribute("aria-busy", disabled ? "true" : "false");
  for (const element of document.querySelectorAll("button, input, select, textarea")) {
    element.disabled = disabled;
  }
  loadingCallbacks.updateGlobalActionState();
  loadingCallbacks.updateDeleteProblemButton();
}

/**
 * showLoading 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function showLoading(message = "작업을 처리하는 중입니다.") {
  state.loadingDepth += 1;
  setText("loadingTitle", "로딩 중");
  setText("loadingMessage", message);
  if (!state.progress.active) loadingCallbacks.renderProgressPanel();
  $("loadingOverlay").classList.remove("hidden");
  setControlsDisabled(true);
}

/**
 * hideLoading 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function hideLoading() {
  state.loadingDepth = Math.max(0, state.loadingDepth - 1);
  if (state.loadingDepth > 0) return;
  $("loadingOverlay").classList.add("hidden");
  loadingCallbacks.completeProgress();
  setControlsDisabled(false);
  loadingCallbacks.updateSolutionPreview();
  loadingCallbacks.updateSolutionRenamePreview();
}

/**
 * forceHideLoading 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function forceHideLoading() {
  state.loadingDepth = 0;
  $("loadingOverlay").classList.add("hidden");
  loadingCallbacks.completeProgress();
  setControlsDisabled(false);
}

/**
 * withLoading 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @param {any} action `action` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function withLoading(message, action) {
  showLoading(message);
  try {
    return await action();
  } finally {
    hideLoading();
  }
}

/**
 * withErrors 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} action `action` 값입니다.
 * @param {any} message 메시지입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function withErrors(action, message = "작업을 처리하는 중입니다.") {
  try {
    return await withLoading(message, action);
  } catch (error) {
    forceHideLoading();
    const title = message.replace(/ 작업을 실행하는 중입니다\.?$/, " 실패").replace(/하는 중입니다\.?$/, " 실패");
    showAlert(error.message, "error", { title: title || "작업 실패", timeout: 9000 });
    return null;
  }
}

/**
 * withInlineErrors 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} action `action` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function withInlineErrors(action) {
  try {
    return await action();
  } catch (error) {
    forceHideLoading();
    showAlert(error.message, "error", { title: "작업 실패", timeout: 9000 });
    return null;
  }
}
