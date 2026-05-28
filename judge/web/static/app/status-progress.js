const app = window.AljApp;
const { state } = app;

/**
 * setGenerationProgress 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} current `current` 값입니다.
 * @param {any} total `total` 값입니다.
 * @param {any} label `label` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function setGenerationProgress(current, total, label = "Data generation") {
  const progress = app.optional("generationProgress");
  if (!progress) return;
  const safeTotal = Math.max(0, Number(total) || 0);
  const safeCurrent = Math.min(Math.max(0, Number(current) || 0), safeTotal || 0);
  state.generationProgress = { current: safeCurrent, total: safeTotal };
  const percent = safeTotal ? Math.round((safeCurrent / safeTotal) * 100) : 0;
  progress.classList.remove("hidden");
  progress.setAttribute("aria-valuemax", String(safeTotal));
  progress.setAttribute("aria-valuenow", String(safeCurrent));
  app.setText("generationProgressText", `${safeCurrent} / ${safeTotal}`);
  const fill = app.optional("generationProgressFill");
  if (fill) fill.style.width = `${percent}%`;
  const labelElement = progress.querySelector(".progress-heading span");
  if (labelElement) labelElement.textContent = label;
}

/**
 * hideGenerationProgress 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function hideGenerationProgress() {
  app.optional("generationProgress")?.classList.add("hidden");
  state.generationProgress = { current: 0, total: 0 };
}

/**
 * updateProgressFromLog 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function updateProgressFromLog(message) {
  const generatedCase = message.match(/Validating generated case .+ \((\d+)\/(\d+)\)\./);
  if (message.includes("Compiling cases.yml")) {
    app.setStatusCard("cases", "Checking", `${app.judgeProfile()} cases.yml`);
  } else if (message.includes("Preparing generator tools")) {
    app.setStatusCard("data", "Preparing", app.judgeProfile());
  } else if (message.includes("Generating input cases")) {
    const total = state.generationProgress.total;
    setGenerationProgress(0, total, "Data generation");
    app.setStatusCard("data", "Generating", total ? `0 / ${app.profileCaseText(total)}` : app.judgeProfile());
  } else if (generatedCase) {
    const current = Number(generatedCase[1]);
    const total = Number(generatedCase[2]);
    setGenerationProgress(current, total, "Data generation");
    app.setStatusCard("data", "Generating", `${current} / ${app.profileCaseText(total)}`);
  } else if (message.includes("Generated data")) {
    const { total } = state.generationProgress;
    if (total) setGenerationProgress(total, total, "Data generation");
    app.setStatusCard("data", "Generated", app.judgeProfile());
  } else if (message.includes("Using cached data")) {
    hideGenerationProgress();
    app.setStatusCard("data", "Ready", app.judgeProfile());
  } else if (message.includes("Preparing submission file")) {
    app.setStatusCard("judge", "Preparing", app.activeSourceName());
  } else if (message.includes("Compiling or preparing user submission")) {
    app.setStatusCard("judge", "Compiling", app.activeSourceName());
  } else if (message.includes("Running case")) {
    app.setStatusCard("judge", "Running", message.replace("Running case ", ""));
  } else if (message.includes("Accepted after")) {
    app.setStatusCard("judge", "Accepted", message);
  }
}

Object.assign(app, {
  hideGenerationProgress,
  setGenerationProgress,
  updateProgressFromLog,
});
