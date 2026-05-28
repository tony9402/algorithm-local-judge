const app = window.AljApp;
const { state } = app;

/**
 * resetRunStatus 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function resetRunStatus(message = "Ready.") {
  app.setBadge("Idle", "neutral");
  app.setText("resultMeta", "No run yet.");
  app.setStatusCard("cases", "Idle", `${app.judgeProfile()} cases.yml plan`);
  app.setStatusCard("data", "Idle", `${app.judgeProfile()} judge data`);
  app.setStatusCard("judge", "Idle");
  app.setStatusCard("run", "-", "No run");
  app.hideGenerationProgress();
  app.setSummary(message, "result-summary muted");
}

/**
 * renderDebugLog 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function renderDebugLog() {
  const output = app.optional("resultOutput");
  if (!output) return;
  const debugToggle = app.optional("debugModeInput");
  const shouldShow = Boolean(state.config?.webDebug) && Boolean(debugToggle?.checked);
  output.textContent = state.debugLogs.join("\n");
  output.classList.toggle("hidden", !shouldShow);
}

/**
 * clearDebugLog 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function clearDebugLog() {
  state.debugLogs = [];
  renderDebugLog();
}

/**
 * configureDebugUi 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function configureDebugUi() {
  const toggle = app.optional("debugToggle");
  const input = app.optional("debugModeInput");
  const enabled = Boolean(state.config?.webDebug);
  if (toggle) toggle.classList.toggle("hidden", !enabled);
  if (input && !enabled) input.checked = false;
  renderDebugLog();
}

/**
 * appendRunLog 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function appendRunLog(message) {
  state.debugLogs.push(message);
  renderDebugLog();
  app.updateProgressFromLog(message);
  const output = app.optional("resultOutput");
  if (output) output.scrollTop = output.scrollHeight;
}

/**
 * showError 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function showError(message) {
  const packModal = app.optional("packModal");
  const cacheModal = app.optional("cacheModal");
  const packOpen = packModal && !packModal.classList.contains("hidden");
  const cacheOpen = cacheModal && !cacheModal.classList.contains("hidden");
  if (packOpen) {
    app.$("packStatus").textContent = message;
    app.$("packStatus").className = "modal-status error";
  }
  if (cacheOpen) {
    app.$("cacheOutput").textContent = message;
    app.$("cacheOutput").className = "modal-status error";
  }
  if (packOpen || cacheOpen) {
    app.showToast(message, "error");
    return;
  }
  app.setBadge("Error", "wrong");
  app.setSummary(message, "result-summary error");
  state.debugLogs.push(`Error: ${message}`);
  renderDebugLog();
}

/**
 * withErrors 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} action `action` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function withErrors(action) {
  app.setBusy(true);
  try {
    await action();
  } catch (error) {
    showError(error.message);
  } finally {
    app.setBusy(false);
  }
}

/**
 * withJobErrors 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} action `action` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function withJobErrors(action) {
  try {
    await action();
  } catch (error) {
    showError(error.message);
  }
}

Object.assign(app, {
  appendRunLog,
  clearDebugLog,
  configureDebugUi,
  renderDebugLog,
  resetRunStatus,
  showError,
  withErrors,
  withJobErrors,
});
