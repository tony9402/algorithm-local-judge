const app = window.AljApp;
const { state } = app;

/**
 * setBusy 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} isBusy `isBusy` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function setBusy(isBusy) {
  state.isBusy = isBusy;
  app.setDisabled("addProblemButton", isBusy);
  app.setDisabled("cacheManageButton", isBusy);
  app.setDisabled("cachePreviewButton", isBusy);
  app.setDisabled("cacheClearRunsButton", isBusy);
  app.setDisabled("cacheClearAllButton", isBusy);
  app.updateActionState?.();
  app.updatePackActionState?.();
}

/**
 * setBadge 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} label `label` 값입니다.
 * @param {any} className `className` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function setBadge(label, className = "neutral") {
  app.setText("statusBadge", label);
  const badge = app.optional("statusBadge");
  if (badge) badge.className = `badge ${className}`;
}

/**
 * setStatusCard 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} key `key` 값입니다.
 * @param {any} value 값입니다.
 * @param {any} meta `meta` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function setStatusCard(key, value, meta = "-") {
  app.setText(`${key}StatusValue`, value);
  app.setText(`${key}StatusMeta`, meta);
}

/**
 * setSummary 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @param {any} className `className` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function setSummary(message, className = "result-summary") {
  const summary = app.optional("resultSummary");
  if (!summary) {
    app.setText("resultOutput", message);
    return;
  }
  summary.textContent = message;
  summary.className = className;
}

Object.assign(app, {
  setBadge,
  setBusy,
  setStatusCard,
  setSummary,
});
