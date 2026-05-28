/**
 * 진행 상태 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { $, escapeHtml, optional, setText } from "./dom.js";
import { persistProblemLastResult } from "./results.js";
import { state } from "./state.js";

function statusLabel(status) {
  if (status === "success") return "완료";
  if (status === "running") return "진행 중";
  if (status === "error") return "실패";
  if (status === "cached") return "캐시 사용";
  return "대기";
}
function progressDoneCount() {
  return state.progress.steps.filter((step) => ["success", "cached"].includes(step.status)).length;
}
function explicitProgressPercent() {
  const percent = Number(state.progress.percent);
  if (!Number.isFinite(percent)) return null;
  return Math.max(0, Math.min(100, Math.round(percent)));
}

function defaultProgressPercent(done, total) {
  return Math.round((done / total) * 100);
}
/**
 * 진행 상태 panel 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
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
export function completeProgress() {
  state.progress.active = false;
  renderProgressPanel();
}
/**
 * 진행 상태 insight 값을 내부 상태나 DOM 요소에 반영합니다.
 *
 * @param {any} title 진행 상태 insight을 계산하거나 검증할 때 필요한 title 입력입니다.
 * @param {any} body API 요청 본문을 검증한 스키마 객체입니다.
 */
export function setProgressInsight(title, body) {
  state.progress.insightTitle = title || "현재 작업";
  state.progress.insightBody = body || "단계가 완료되면 결과 요약이 갱신됩니다.";
  renderProgressPanel();
}
/**
 * 진행 상태 step 값을 내부 상태나 DOM 요소에 반영합니다.
 *
 * @param {any} index 진행 상태 step을 계산하거나 검증할 때 필요한 index 입력입니다.
 * @param {Array} status 진행 상태 step을 계산하거나 검증할 때 필요한 상태 입력입니다.
 * @param {any} detail 진행 상태 step을 계산하거나 검증할 때 필요한 detail 입력입니다.
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
 * running 진행 상태 detail 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 *
 * @param {any} detail running 진행 상태 detail을 계산하거나 검증할 때 필요한 detail 입력입니다.
 */
export function updateRunningProgressDetail(detail) {
  const runningIndex = state.progress.steps.findIndex((step) => step.status === "running");
  if (runningIndex < 0) return;
  state.progress.steps[runningIndex].detail = detail;
  renderProgressPanel();
}
/**
 * 진행 상태 작업 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 *
 * @param {object} job 진행 상태 작업을 계산하거나 검증할 때 필요한 작업 입력입니다.
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
export function hideLastRunPanel() {
  optional("lastRunPanel")?.classList.add("hidden");
}
function shouldDisplayLastRunPanel(tabId = state.selectedTab) {
  return tabId !== "build" && tabId !== "solutions";
}
/**
 * last 실행 panel 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
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
export function showLastRun(title, summary, type = "success", options = {}) {
  state.lastRun = { title, summary, type, updatedAt: Date.now() };
  if (options.persist !== false) {
    persistProblemLastResult({ lastRun: state.lastRun }, options.problemId);
  }
  renderLastRunPanel();
}
