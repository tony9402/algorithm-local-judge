/**
 * 상태 debug 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;

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
 * debug log 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
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
 * debug log 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 */
function clearDebugLog() {
  state.debugLogs = [];
  renderDebugLog();
}
function configureDebugUi() {
  const toggle = app.optional("debugToggle");
  const input = app.optional("debugModeInput");
  const enabled = Boolean(state.config?.webDebug);
  if (toggle) toggle.classList.toggle("hidden", !enabled);
  if (input && !enabled) input.checked = false;
  renderDebugLog();
}
function appendRunLog(message) {
  state.debugLogs.push(message);
  renderDebugLog();
  app.updateProgressFromLog(message);
  const output = app.optional("resultOutput");
  if (output) output.scrollTop = output.scrollHeight;
}
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

async function withJobErrors(action) {
  try {
    await action();
  } catch (error) {
    if (error.status === 429 && error.detail?.retryAfterSeconds) {
      app.recordSubmissionCooldown?.(app.$("problemSelect")?.value, error.detail.retryAfterSeconds);
    }
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
