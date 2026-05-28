/**
 * loading 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { $, setText } from "./dom.js";
import { showAlert } from "./feedback.js";
import { state } from "./state.js";

const loadingCallbacks = {
  completeProgress: () => {},
  renderProgressPanel: () => {},
  updateDeleteProblemButton: () => {},
  updateGlobalActionState: () => {},
  updateSolutionPreview: () => {},
  updateSolutionRenamePreview: () => {},
};
export function configureLoading(callbacks = {}) {
  Object.assign(loadingCallbacks, callbacks);
}

function setControlsDisabled(disabled) {
  document.body.setAttribute("aria-busy", disabled ? "true" : "false");
  for (const element of document.querySelectorAll("button, input, select, textarea")) {
    element.disabled = disabled;
  }
  loadingCallbacks.updateGlobalActionState();
  loadingCallbacks.updateDeleteProblemButton();
}
function showLoading(message = "작업을 처리하는 중입니다.") {
  state.loadingDepth += 1;
  setText("loadingTitle", "로딩 중");
  setText("loadingMessage", message);
  if (!state.progress.active) loadingCallbacks.renderProgressPanel();
  $("loadingOverlay").classList.remove("hidden");
  setControlsDisabled(true);
}
function hideLoading() {
  state.loadingDepth = Math.max(0, state.loadingDepth - 1);
  if (state.loadingDepth > 0) return;
  $("loadingOverlay").classList.add("hidden");
  loadingCallbacks.completeProgress();
  setControlsDisabled(false);
  loadingCallbacks.updateSolutionPreview();
  loadingCallbacks.updateSolutionRenamePreview();
}
export function forceHideLoading() {
  state.loadingDepth = 0;
  $("loadingOverlay").classList.add("hidden");
  loadingCallbacks.completeProgress();
  setControlsDisabled(false);
}

async function withLoading(message, action) {
  showLoading(message);
  try {
    return await action();
  } finally {
    hideLoading();
  }
}
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
export async function withInlineErrors(action) {
  try {
    return await action();
  } catch (error) {
    forceHideLoading();
    showAlert(error.message, "error", { title: "작업 실패", timeout: 9000 });
    return null;
  }
}
