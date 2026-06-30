/**
 * 상태 ui 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;
/**
 * busy 값을 내부 상태나 DOM 요소에 반영합니다.
 *
 * @param {boolean} isBusy busy을 계산하거나 검증할 때 필요한 is busy 입력입니다.
 */
function setBusy(isBusy) {
  state.isBusy = isBusy;
  app.setDisabled("addProblemButton", isBusy);
  app.setDisabled("topAddProblemButton", isBusy);
  app.setDisabled("cacheManageButton", isBusy);
  app.setDisabled("cachePreviewButton", isBusy);
  app.setDisabled("cacheClearRunsButton", isBusy);
  app.setDisabled("cacheClearAllButton", isBusy);
  app.updateActionState?.();
  app.updatePackActionState?.();
}

function setBadge(label, className = "neutral") {
  app.setText("statusBadge", label);
  const badge = app.optional("statusBadge");
  if (badge) badge.className = `badge ${className}`;
}

function setStatusCard(key, value, meta = "-") {
  app.setText(`${key}StatusValue`, value);
  app.setText(`${key}StatusMeta`, meta);
}

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
