const app = window.AljApp;
const { state } = app;

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
