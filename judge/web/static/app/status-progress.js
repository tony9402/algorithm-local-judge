/**
 * 상태 진행 상태 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;
/**
 * 생성 진행 상태 값을 내부 상태나 DOM 요소에 반영합니다.
 *
 * @param {any} current 생성 진행 상태을 계산하거나 검증할 때 필요한 현재 입력입니다.
 * @param {any} total 생성 진행 상태을 계산하거나 검증할 때 필요한 total 입력입니다.
 * @param {string} label 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
 */
function setGenerationProgress(current, total, label = "데이터 생성") {
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
function hideGenerationProgress() {
  app.optional("generationProgress")?.classList.add("hidden");
  state.generationProgress = { current: 0, total: 0 };
}
/**
 * 진행 상태 log 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 *
 * @param {string} message 사용자에게 표시하거나 커밋/진행 상태에 기록할 메시지입니다.
 */
function updateProgressFromLog(message) {
  const generatedCase = message.match(/Validating generated case .+ \((\d+)\/(\d+)\)\./);
  if (message.includes("Compiling cases.yml")) {
    app.setStatusCard("cases", "검사 중", `${app.judgeProfile()} cases.yml`);
  } else if (message.includes("Preparing generator tools")) {
    app.setStatusCard("data", "준비 중", app.judgeProfile());
  } else if (message.includes("Generating input cases")) {
    const total = state.generationProgress.total;
    setGenerationProgress(0, total, "데이터 생성");
    app.setStatusCard("data", "생성 중", total ? `0 / ${app.profileCaseText(total)}` : app.judgeProfile());
  } else if (generatedCase) {
    const current = Number(generatedCase[1]);
    const total = Number(generatedCase[2]);
    setGenerationProgress(current, total, "데이터 생성");
    app.setStatusCard("data", "생성 중", `${current} / ${app.profileCaseText(total)}`);
  } else if (message.includes("Generated data")) {
    const { total } = state.generationProgress;
    if (total) setGenerationProgress(total, total, "데이터 생성");
    app.setStatusCard("data", "생성 완료", app.judgeProfile());
  } else if (message.includes("Using cached data")) {
    hideGenerationProgress();
    app.setStatusCard("data", "준비됨", app.judgeProfile());
  } else if (message.includes("Preparing submission file")) {
    app.setStatusCard("judge", "준비 중", app.activeSourceName());
  } else if (message.includes("Compiling or preparing user submission")) {
    app.setStatusCard("judge", "컴파일 중", app.activeSourceName());
  } else if (message.includes("Running case")) {
    app.setStatusCard("judge", "실행 중", message.replace("Running case ", ""));
  } else if (message.includes("Accepted after")) {
    app.setStatusCard("judge", "맞았습니다", message);
  }
}

Object.assign(app, {
  hideGenerationProgress,
  setGenerationProgress,
  updateProgressFromLog,
});
