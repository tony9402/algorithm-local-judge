import { $, escapeHtml, optional, setText } from "./dom.js";
import { persistProblemLastResult } from "./results.js";
import { state } from "./state.js";

/**
 * statusLabel 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} status `status` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function statusLabel(status) {
  if (status === "success") return "완료";
  if (status === "running") return "진행 중";
  if (status === "error") return "실패";
  if (status === "cached") return "캐시 사용";
  return "대기";
}

/**
 * progressDoneCount 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function progressDoneCount() {
  return state.progress.steps.filter((step) => ["success", "cached"].includes(step.status)).length;
}

/**
 * explicitProgressPercent 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function explicitProgressPercent() {
  const percent = Number(state.progress.percent);
  if (!Number.isFinite(percent)) return null;
  return Math.max(0, Math.min(100, Math.round(percent)));
}

/**
 * defaultProgressPercent 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} done `done` 값입니다.
 * @param {any} total `total` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function defaultProgressPercent(done, total) {
  return Math.round((done / total) * 100);
}

/**
 * renderProgressPanel 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function renderProgressPanel() {
  const panel = optional("progressPanel");
  if (!panel) return;
  panel.classList.toggle("hidden", !state.progress.active);
  if (!state.progress.active) return;

  const steps = state.progress.steps;
  const total = Math.max(steps.length, 1);
  const done = progressDoneCount();
  const percent = explicitProgressPercent() ?? defaultProgressPercent(done, total);
  const fill = optional("progressBarFill");
  if (fill) fill.style.width = `${percent}%`;
  const bar = document.querySelector(".progress-bar");
  if (bar) {
    bar.removeAttribute("aria-hidden");
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.setAttribute("aria-valuenow", String(percent));
    bar.setAttribute("aria-label", `${percent}% 진행`);
  }

  const running = steps.find((step) => step.status === "running");
  const failed = steps.find((step) => step.status === "error");
  const summary = failed
    ? `${percent}% · ${failed.label} 단계에서 확인이 필요합니다.`
    : running
      ? `${percent}% · ${running.label} 진행 중 · ${done}/${steps.length}단계 완료`
      : `${percent}% · ${done}/${steps.length}단계 완료`;
  setText("progressSummary", summary);
  setText("progressInsightTitle", state.progress.insightTitle || "현재 작업");
  setText(
    "progressInsightBody",
    state.progress.insightBody || "단계가 완료되면 결과 요약이 갱신됩니다."
  );

  $("progressSteps").innerHTML = steps
    .map(
      (step) => `
        <li class="${step.status}">
          <span class="progress-dot" aria-hidden="true"></span>
          <div>
            <strong>${escapeHtml(step.label)}</strong>
            <span>${statusLabel(step.status)}</span>
            ${step.detail ? `<p>${escapeHtml(step.detail)}</p>` : ""}
          </div>
        </li>
      `
    )
    .join("");
}

/**
 * beginProgress 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} title `title` 값입니다.
 * @param {any} steps `steps` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function beginProgress(title, steps = []) {
  state.progress = {
    active: true,
    title,
    steps: steps.map((step) => ({ ...step })),
    percent: 0,
    insightTitle: "현재 작업",
    insightBody: "전체 테스트를 준비하고 있습니다.",
  };
  setText("loadingTitle", title);
  setText("loadingMessage", "단계별 진행 상황을 확인하고 있습니다.");
  renderProgressPanel();
}

/**
 * completeProgress 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function completeProgress() {
  state.progress.active = false;
  renderProgressPanel();
}

/**
 * setProgressInsight 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} title `title` 값입니다.
 * @param {any} body `body` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function setProgressInsight(title, body) {
  state.progress.insightTitle = title || "현재 작업";
  state.progress.insightBody = body || "단계가 완료되면 결과 요약이 갱신됩니다.";
  renderProgressPanel();
}

/**
 * setProgressStep 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} index `index` 값입니다.
 * @param {any} status `status` 값입니다.
 * @param {any} detail `detail` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function setProgressStep(index, status, detail = "") {
  if (!state.progress.steps[index]) return;
  state.progress.steps[index].status = status;
  state.progress.steps[index].detail = detail;
  state.progress.percent = null;
  const running = state.progress.steps.find((step) => step.status === "running");
  const done = progressDoneCount();
  setText("loadingTitle", state.progress.title || "진행 중");
  setText("loadingMessage", running ? running.label : `${done}/${state.progress.steps.length} 완료`);
  renderProgressPanel();
}

/**
 * updateRunningProgressDetail 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} detail `detail` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function updateRunningProgressDetail(detail) {
  const runningIndex = state.progress.steps.findIndex((step) => step.status === "running");
  if (runningIndex < 0) return;
  state.progress.steps[runningIndex].detail = detail;
  renderProgressPanel();
}

/**
 * updateProgressFromJob 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} job `job` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function updateProgressFromJob(job) {
  if (!state.progress.active || !job) return;
  const progress = job.progress || {};
  const current = Number(progress.current);
  const total = Number(progress.total);
  const detail = progress.message || job.lastLog || "";
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) {
    if (detail) updateRunningProgressDetail(detail);
    return;
  }

  const stepCount = state.progress.steps.length;
  if (stepCount <= 0) return;
  const safeTotal = Math.max(1, total);
  const safeCurrent = Math.max(1, Math.min(safeTotal, current));
  const runningIndex = Math.min(stepCount - 1, Math.max(0, safeCurrent - 1));

  for (const [index, step] of state.progress.steps.entries()) {
    if (step.status === "error") continue;
    if (index < runningIndex) {
      step.status = "success";
    } else if (index === runningIndex) {
      step.status = "running";
      step.detail = detail;
      if (progress.label) step.label = progress.label;
    } else if (!["success", "cached"].includes(step.status)) {
      step.status = "pending";
    }
  }

  state.progress.percent = Math.min(99, Math.round((safeCurrent / safeTotal) * 100));
  setText("loadingTitle", state.progress.title || "진행 중");
  setText("loadingMessage", `${state.progress.percent}% · ${detail || "진행 중"}`);
  renderProgressPanel();
}

/**
 * hideLastRunPanel 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function hideLastRunPanel() {
  optional("lastRunPanel")?.classList.add("hidden");
}

/**
 * shouldDisplayLastRunPanel 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} tabId `tabId` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function shouldDisplayLastRunPanel(tabId = state.selectedTab) {
  return tabId !== "build" && tabId !== "solutions";
}

/**
 * renderLastRunPanel 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function renderLastRunPanel() {
  const panel = optional("lastRunPanel");
  if (!panel) return;
  if (!state.lastRun || !shouldDisplayLastRunPanel()) {
    hideLastRunPanel();
    return;
  }
  panel.className = `last-run-panel ${state.lastRun.type || "info"}`;
  setText("lastRunTitle", state.lastRun.title || "실행 결과");
  setText("lastRunSummary", state.lastRun.summary || "");
}

/**
 * showLastRun 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} title `title` 값입니다.
 * @param {any} summary `summary` 값입니다.
 * @param {any} type `type` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function showLastRun(title, summary, type = "success", options = {}) {
  state.lastRun = { title, summary, type, updatedAt: Date.now() };
  if (options.persist !== false) {
    persistProblemLastResult({ lastRun: state.lastRun }, options.problemId);
  }
  renderLastRunPanel();
}
