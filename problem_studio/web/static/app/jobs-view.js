/**
 * 작업 화면 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { api, normalizeErrorDetail } from "./api.js";
import { optional, escapeHtml } from "./dom.js";
import { showAlert, showOperationAlert } from "./feedback.js";
import { setProgressInsight, updateRunningProgressDetail } from "./progress.js";
import { reconcileRunAllLockWithJobs } from "./actions/build-locks.js";
import { updateGlobalActionState } from "./actions/build-status.js";
import { trapFocusWithin } from "./modal.js";

let jobs = [];
let filter = "active";
let pollTimer = null;
const waiters = new Map();
const expandedJobIds = new Set();
const announcedTerminalJobIds = new Set();
const operationToastJobIds = new Set();
let previousJobStatuses = null;
let jobCenterTrigger = null;

const jobViewCallbacks = {
  closeGitDrawer: () => {},
  closeSidebar: () => {},
  openFailureTarget: async () => {},
};

export function configureJobsView(callbacks = {}) {
  Object.assign(jobViewCallbacks, callbacks);
}

const ACTIVE = new Set(["queued", "running", "cancelling"]);
const DONE = new Set(["succeeded", "cancelled", "stale"]);

function statusLabel(status) {
  return {
    queued: "대기 중",
    running: "실행 중",
    cancelling: "취소 요청됨",
    succeeded: "완료",
    failed: "실패",
    cancelled: "취소됨",
    stale: "만료됨",
  }[status] || status;
}

function jobCounts() {
  return {
    active: jobs.filter((job) => ACTIVE.has(job.status)).length,
    done: jobs.filter((job) => DONE.has(job.status)).length,
    running: jobs.filter((job) => job.status === "running" || job.status === "cancelling").length,
    queued: jobs.filter((job) => job.status === "queued").length,
    failed: jobs.filter(jobNeedsAttention).length,
  };
}

function visibleJobs() {
  if (filter === "active") return jobs.filter((job) => ACTIVE.has(job.status));
  if (filter === "failed") return jobs.filter(jobNeedsAttention);
  return jobs.filter((job) => DONE.has(job.status));
}

function failureDetails(job) {
  if (Array.isArray(job.failureDetails) && job.failureDetails.length) {
    return job.failureDetails;
  }
  if (Array.isArray(job.result?.failureDetails) && job.result.failureDetails.length) {
    return job.result.failureDetails;
  }
  return [];
}

function jobOutcome(job) {
  if (job.outcome) return job.outcome;
  if (ACTIVE.has(job.status)) return "pending";
  if (job.status === "cancelled") return "cancelled";
  if (job.status === "stale") return "stale";
  if (job.status === "failed" || job.result?.passed === false || failureDetails(job).length) {
    return "failed";
  }
  if (job.status === "succeeded") return "passed";
  return job.status || "pending";
}

function jobNeedsAttention(job) {
  return jobOutcome(job) === "failed";
}

function jobDisplayStatus(job) {
  if (jobNeedsAttention(job)) return "failed";
  return job.status || "queued";
}

function jobDisplayLabel(job) {
  if (jobNeedsAttention(job) && job.status === "succeeded") return "검증 실패";
  if (jobNeedsAttention(job)) return "실패";
  return statusLabel(job.status);
}

function formatTarget(job) {
  const target = job.target || {};
  return [
    target.problemId || job.problemId,
    target.profile,
    target.tool,
    target.packId,
    target.source,
  ].filter(Boolean).join(" · ");
}

function progressPercent(job) {
  const progress = job.progress || {};
  const current = Number(progress.current);
  const total = Number(progress.total);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return null;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

function visualProgressPercent(job, percent) {
  if (percent !== null) return percent;
  if (job.status === "queued") return 14;
  if (["succeeded", "failed", "cancelled", "stale"].includes(job.status)) return 100;
  return 0;
}

function progressTrackClass(job, percent) {
  const classes = ["job-progress-track"];
  if (percent === null && ["running", "cancelling"].includes(job.status)) classes.push("indeterminate");
  return classes.join(" ");
}

function progressAriaAttrs(job, percent, active) {
  if (percent !== null) {
    return `role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}" aria-label="${escapeHtml(jobDisplayLabel(job))}"`;
  }
  if (active && job.status !== "queued") {
    return `role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-label="${escapeHtml(jobDisplayLabel(job))}"`;
  }
  return `aria-hidden="true"`;
}

function formatTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

function formatSeconds(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "";
  if (numeric >= 60) return `${Math.floor(numeric / 60)}m ${Math.round(numeric % 60)}s`;
  return `${Math.round(numeric)}s`;
}

function progressDetails(job, percent) {
  const progress = job.progress || {};
  const details = [];
  if (percent !== null) details.push(`${percent}%`);
  if (progress.iteration !== undefined) details.push(`반복 ${progress.iteration}`);
  if (progress.elapsedSeconds !== undefined) details.push(`경과 ${formatSeconds(progress.elapsedSeconds)}`);
  if (progress.remainingSeconds !== undefined) details.push(`남음 ${formatSeconds(progress.remainingSeconds)}`);
  if (progress.seed !== undefined && progress.seed !== null) details.push(`seed ${progress.seed}`);
  if (progress.mismatches !== undefined) details.push(`mismatch ${progress.mismatches}`);
  return details.filter(Boolean).join(" · ");
}

function detailTarget(detail) {
  return [
    detail.problemId,
    detail.source || detail.path || detail.sourcePath,
    detail.target,
    detail.expectedStatus && detail.actualStatus
      ? `기대 ${detail.expectedStatus} · 실제 ${detail.actualStatus}`
      : "",
    detail.runId ? `run ${detail.runId}` : "",
  ].filter(Boolean).join(" · ");
}

function failureSummary(job) {
  const detail = failureDetails(job)[0] || {};
  return [
    job.failureStageLabel || job.result?.failureStageLabel || detail.label,
    detailTarget(detail),
    detail.message || job.error,
  ].filter(Boolean).join(" · ");
}
function safeDomId(value) {
  return String(value || "job").replace(/[^A-Za-z0-9_-]/g, "-");
}
function jobResultPanelId(job) {
  return `job-result-${safeDomId(job.jobId)}`;
}
function jobResultSummary(job) {
  const result = job.result || {};
  return (
    failureSummary(job)
    || result.summary
    || result.message
    || job.lastLog
    || job.error
    || "작업 결과가 준비되었습니다."
  );
}
function renderJobResultPanel(job, expanded) {
  if (!expanded) return "";
  const details = failureDetails(job);
  const result = job.result ? JSON.stringify(job.result, null, 2) : "";
  const title = jobNeedsAttention(job) ? "실패 상세" : "결과 상세";
  return `
    <section
      id="${escapeHtml(jobResultPanelId(job))}"
      class="job-result-panel ${jobNeedsAttention(job) ? "error" : "success"}"
      tabindex="-1"
      aria-label="${escapeHtml(`${job.title || "작업"} ${title}`)}"
    >
      <div class="job-result-heading">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(formatTarget(job) || job.kind || "")}</span>
      </div>
      <p>${escapeHtml(jobResultSummary(job))}</p>
      ${
        details.length
          ? `<ul class="job-result-detail-list">
              ${details.map((detail, index) => `
                <li>
                  <strong>${escapeHtml(detail.label || job.failureStageLabel || "실패 상세")}</strong>
                  ${detailTarget(detail) ? `<span>${escapeHtml(detailTarget(detail))}</span>` : ""}
                  ${detail.message ? `<p>${escapeHtml(detail.message)}</p>` : ""}
                  ${renderFailureActions(job, detail, index)}
                </li>
              `).join("")}
            </ul>`
          : ""
      }
      ${
        job.error && !details.length
          ? `<pre class="job-result-raw">${escapeHtml(job.error)}</pre>`
          : ""
      }
      ${
        result
          ? `<details class="job-result-raw-block">
              <summary>원본 결과</summary>
              <pre>${escapeHtml(result)}</pre>
            </details>`
          : ""
      }
    </section>
  `;
}

function renderFailureActions(job, detail, index) {
  const source = detail.source || detail.path || detail.sourcePath || "";
  const solution = String(source).includes("solutions/");
  const buttons = [];
  if (source) {
    buttons.push(`<button type="button" data-job-failure-action="file" data-job-id="${escapeHtml(job.jobId)}" data-detail-index="${index}">파일 열기</button>`);
  }
  if (solution) {
    buttons.push(`<button type="button" data-job-failure-action="solution" data-job-id="${escapeHtml(job.jobId)}" data-detail-index="${index}">솔루션 행</button>`);
  }
  if (solution && detail.runId) {
    buttons.push(`<button type="button" data-job-failure-action="artifact" data-job-id="${escapeHtml(job.jobId)}" data-detail-index="${index}">채점 결과</button>`);
  }
  return buttons.length ? `<div class="job-failure-actions">${buttons.join("")}</div>` : "";
}

function renderFailureDetails(job) {
  const details = failureDetails(job);
  if (!jobNeedsAttention(job) && !details.length) return "";
  const items = details.length
    ? details.map((detail, index) => `
        <li>
          <strong>${escapeHtml(detail.label || job.failureStageLabel || "실패 상세")}</strong>
          ${detailTarget(detail) ? `<span>${escapeHtml(detailTarget(detail))}</span>` : ""}
          ${detail.message ? `<p>${escapeHtml(detail.message)}</p>` : ""}
          ${renderFailureActions(job, detail, index)}
        </li>
      `).join("")
    : `<li><strong>${escapeHtml(job.failureStageLabel || "실패 상세")}</strong><p>${escapeHtml(job.error || "작업이 실패했습니다.")}</p></li>`;
  return `<ul class="job-failure-detail">${items}</ul>`;
}

function renderJobLogs(job) {
  const logs = Array.isArray(job.logs) ? job.logs.filter((item) => item?.message) : [];
  if (!logs.length) return "";
  const ordered = logs.slice().reverse();
  return `
    <details class="job-log-list">
      <summary>로그 ${escapeHtml(logs.length)}개</summary>
      <ol>
        ${ordered.map((item) => `<li>${escapeHtml(item.message)}</li>`).join("")}
      </ol>
    </details>
  `;
}
/**
 * summary 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderSummary() {
  const button = optional("jobCenterButton");
  const meta = optional("jobCenterMeta");
  const counts = jobCounts();
  const text = counts.active
    ? `작업 ${counts.active}개 · 실행 ${counts.running} · 대기 ${counts.queued}`
    : counts.failed
      ? `실패 ${counts.failed}개 확인`
      : "작업 0개";
  if (button) button.textContent = text;
  if (meta) {
    meta.textContent = counts.active
      ? `실행 중 ${counts.running}개, 대기 ${counts.queued}개`
      : counts.failed
        ? `실패한 작업 ${counts.failed}개가 있습니다.`
        : "실행 중인 작업이 없습니다.";
  }
  for (const item of document.querySelectorAll("[data-job-filter]")) {
    const value = item.dataset.jobFilter || "active";
    const label = value === "failed" ? "실패" : value === "done" ? "완료" : "진행";
    const count = value === "failed" ? counts.failed : value === "done" ? counts.done : counts.active;
    item.innerHTML = `${escapeHtml(label)} <span class="job-filter-count">${escapeHtml(count)}</span>`;
  }
}
/**
 * 작업 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderJobs() {
  renderSummary();
  const list = optional("jobCenterList");
  if (!list) return;
  const items = visibleJobs();
  list.classList.toggle("muted", !items.length);
  if (!items.length) {
    list.innerHTML = escapeHtml("") + `
      <div class="job-empty-state">
        <strong>${filter === "failed" ? "실패한 작업이 없습니다." : filter === "done" ? "완료된 작업이 없습니다." : "진행 중인 작업이 없습니다."}</strong>
        <span>새 작업이 시작되면 이곳에 상태와 로그가 표시됩니다.</span>
      </div>
    `;
    return;
  }
  list.innerHTML = escapeHtml("") + items.map(renderJobRow).join("");
}
function renderJobRow(job) {
  const percent = progressPercent(job);
  const active = ["queued", "running", "cancelling"].includes(job.status);
  const blockedCancel = active && job.cancelMode === "blocked" && job.cancelBlockedReason;
  const canCancel = job.cancelSupported && ["queued", "running"].includes(job.status);
  const cancelling = job.status === "cancelling";
  const terminal = ["succeeded", "failed", "cancelled", "stale"].includes(job.status);
  const visualPercent = visualProgressPercent(job, percent);
  const progressClass = progressTrackClass(job, percent);
  const attention = jobNeedsAttention(job);
  const displayStatus = jobDisplayStatus(job);
  const expanded = expandedJobIds.has(job.jobId);
  const resultButton = terminal && (job.result || job.error || failureDetails(job).length)
    ? `<button
        type="button"
        data-job-result="${escapeHtml(job.jobId)}"
        aria-expanded="${expanded ? "true" : "false"}"
        aria-controls="${escapeHtml(jobResultPanelId(job))}"
      >${expanded ? "상세 닫기" : attention ? "상세 보기" : "결과 보기"}</button>`
    : "";
  const cancelButton = canCancel || cancelling
    ? `<button type="button" data-job-cancel="${escapeHtml(job.jobId)}" ${cancelling ? "disabled" : ""}>${cancelling ? "취소 요청됨" : "취소"}</button>`
    : blockedCancel
      ? `<button type="button" disabled title="${escapeHtml(job.cancelBlockedReason)}">취소 불가</button>`
    : "";
  const cancelReason = job.cancelBlockedReason
    ? `<div class="job-cancel-reason">${escapeHtml(job.cancelBlockedReason)}</div>`
    : "";
  const dismissButton = terminal
    ? `<button type="button" data-job-dismiss="${escapeHtml(job.jobId)}">정리</button>`
    : "";
  const progressAttrs = progressAriaAttrs(job, percent, active);
  const details = progressDetails(job, percent);
  const summary = attention ? failureSummary(job) : "";
  return `
    <article class="job-row ${escapeHtml(job.status)} ${attention ? "attention" : ""}" data-job-id="${escapeHtml(job.jobId)}">
      <div class="job-row-header">
        <span class="job-row-title">
          <span class="job-status ${escapeHtml(displayStatus)}" aria-label="${escapeHtml(jobDisplayLabel(job))}">${escapeHtml(jobDisplayLabel(job))}</span>
          ${escapeHtml(job.title || job.kind)}
        </span>
        <span class="job-row-time">${escapeHtml(formatTime(job.startedAt || job.queuedAt))}</span>
      </div>
      <div class="job-row-subheader">
        <span class="job-row-target">${escapeHtml(formatTarget(job) || job.kind)}</span>
      </div>
      <div class="${escapeHtml(progressClass)}" ${progressAttrs}><span class="job-progress-fill" style="width:${visualPercent}%"></span></div>
      ${details ? `<div class="job-progress-meta">${escapeHtml(details)}</div>` : ""}
      ${summary ? `<div class="job-row-log job-outcome">${escapeHtml(summary)}</div>` : ""}
      <div class="job-row-log">${escapeHtml(job.lastLog || job.progress?.message || job.error || "")}</div>
      ${renderFailureDetails(job)}
      ${renderJobLogs(job)}
      ${renderJobResultPanel(job, expanded)}
      ${cancelReason}
      <div class="job-row-actions">${cancelButton}${resultButton}${dismissButton}</div>
    </article>
  `;
}
/**
 * 작업 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 */
async function refreshJobs() {
  try {
    const payload = await api("/api/jobs");
    const nextJobs = payload.jobs || [];
    announceTerminalTransitions(nextJobs);
    for (const job of nextJobs) syncOperationToast(job);
    jobs = nextJobs;
    if (reconcileRunAllLockWithJobs(jobs)) updateGlobalActionState();
    renderJobs();
    await resolveWaiters();
  } finally {
    schedulePoll();
  }
}

function syncOperationToast(job) {
  if (!operationToastJobIds.has(job.jobId)) return;
  const title = job.title || "작업";
  if (job.status === "queued") {
    showOperationAlert(job.jobId, `${title}을 작업 대기열에 추가했습니다.`, "info", {
      title: "작업 대기열",
      timeout: 0,
    });
    return;
  }
  if (["running", "cancelling"].includes(job.status)) {
    const cancelling = job.status === "cancelling";
    showOperationAlert(
      job.jobId,
      cancelling ? `${title} 취소 요청을 처리하고 있습니다.` : `${title}을 실행하고 있습니다.`,
      "info",
      { title: cancelling ? "작업 취소 중" : "작업 실행 중", timeout: 0 }
    );
    return;
  }
  const attention = jobNeedsAttention(job);
  const type = attention || ["cancelled", "stale"].includes(job.status) ? "error" : "success";
  showOperationAlert(
    job.jobId,
    attention ? jobResultSummary(job) : `${title}: ${jobDisplayLabel(job)}`,
    type,
    {
      title: attention ? `${title} 실패` : `${title} ${jobDisplayLabel(job)}`,
      timeout: type === "error" ? 9000 : 5000,
    }
  );
  operationToastJobIds.delete(job.jobId);
}

function announceTerminalTransitions(nextJobs) {
  const nextStatuses = new Map(nextJobs.map((job) => [job.jobId, job.status]));
  if (previousJobStatuses === null) {
    previousJobStatuses = nextStatuses;
    return;
  }
  const announcements = [];
  for (const job of nextJobs) {
    const previous = previousJobStatuses.get(job.jobId);
    const terminal = ["succeeded", "failed", "cancelled", "stale"].includes(job.status);
    if (
      previous
      && ACTIVE.has(previous)
      && terminal
      && !announcedTerminalJobIds.has(job.jobId)
    ) {
      announcedTerminalJobIds.add(job.jobId);
      announcements.push(`${job.title || "작업"}: ${jobDisplayLabel(job)}`);
    }
  }
  previousJobStatuses = nextStatuses;
  if (announcements.length) {
    const region = optional("jobCenterAnnouncements");
    if (region) region.textContent = announcements.join(". ");
  }
}

function schedulePoll(delay = 900) {
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = window.setTimeout(refreshJobs, delay);
}

async function jobForWaiter(jobId, waiter) {
  const visible = jobs.find((item) => item.jobId === jobId);
  if (visible || !waiter.repositoryScope) return visible;
  try {
    return await api(
      `/api/jobs/${encodeURIComponent(jobId)}?repository_scope=${encodeURIComponent(waiter.repositoryScope)}`
    );
  } catch {
    return null;
  }
}
async function resolveWaiters() {
  for (const [jobId, waiter] of waiters.entries()) {
    const job = await jobForWaiter(jobId, waiter);
    if (!job) continue;
    waiter.onProgress?.(job);
    if (job.status === "succeeded") {
      waiters.delete(jobId);
      waiter.resolve(job);
    }
    if (["failed", "cancelled", "stale"].includes(job.status)) {
      waiters.delete(jobId);
      waiter.reject(new Error(normalizeErrorDetail(job.error) || statusLabel(job.status)));
    }
  }
}
export async function runQueuedJob(path, body, options = {}) {
  const job = await api(path, {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
  operationToastJobIds.add(job.jobId);
  syncOperationToast(job);
  await refreshJobs();
  return new Promise((resolve, reject) => {
    waiters.set(job.jobId, {
      repositoryScope: job.target?.repositoryScope || null,
      resolve: (finished) => {
        const result = finished.result || {};
        options.onResult?.(result, finished);
        if (finished.lastLog) updateRunningProgressDetail(finished.lastLog);
        resolve(result);
      },
      reject,
      onProgress: options.onProgress,
    });
    setProgressInsight("작업 센터", `${job.title || "작업"}이 queue에서 실행됩니다.`);
    schedulePoll(250);
  });
}
export async function enqueueQueuedJob(path, body, options = {}) {
  const job = await api(path, {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
  operationToastJobIds.add(job.jobId);
  syncOperationToast(job);
  await refreshJobs();
  if (options.onResult || options.onFailure || options.onProgress) {
    waiters.set(job.jobId, {
      repositoryScope: job.target?.repositoryScope || null,
      resolve: (finished) => {
        const result = finished.result || {};
        options.onResult?.(result, finished);
        if (finished.lastLog) updateRunningProgressDetail(finished.lastLog);
      },
      reject: (error) => {
        if (options.onFailure) {
          options.onFailure(error, job);
        } else {
          showAlert(error.message, "error", {
            title: `${job.title || options.label || "작업"} 실패`,
            timeout: 7000,
          });
        }
      },
      onProgress: options.onProgress,
    });
  }
  setProgressInsight("작업 센터", `${job.title || "작업"}이 queue에서 실행됩니다.`);
  schedulePoll(250);
  return job;
}
async function cancelJob(jobId) {
  const job = jobs.find((item) => item.jobId === jobId);
  await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
  showAlert(`${job?.title || "작업"} 취소를 요청했습니다.`, "info", {
    title: "취소 요청됨",
    timeout: 3500,
  });
  await refreshJobs();
}
async function dismissJob(jobId) {
  expandedJobIds.delete(jobId);
  await api(`/api/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
  await refreshJobs();
}
/**
 * completed 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 */
async function clearCompleted() {
  expandedJobIds.clear();
  await api("/api/jobs/completed", { method: "DELETE" });
  await refreshJobs();
}
/**
 * drawer 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 *
 * @param {boolean} open drawer을 계산하거나 검증할 때 필요한 open 입력입니다.
 */
const COMPACT_SURFACE_QUERY = "(max-width: 1199px)";

export function compactJobCenterActive() {
  return window.matchMedia?.(COMPACT_SURFACE_QUERY).matches ?? false;
}

function setJobBackgroundInert(inert) {
  for (const id of ["sidebarToggle", "sidebarBackdrop", "alertStack"]) {
    optional(id)?.toggleAttribute("inert", inert);
  }
  document.querySelector(".shell")?.toggleAttribute("inert", inert);
}

export function isJobCenterOpen() {
  return !optional("jobCenterDrawer")?.classList.contains("hidden");
}

export function syncJobCenterAccessibility() {
  const drawer = optional("jobCenterDrawer");
  const button = optional("jobCenterButton");
  if (!drawer || !button) return;
  const open = isJobCenterOpen();
  const compact = compactJobCenterActive();
  drawer.setAttribute("role", compact ? "dialog" : "complementary");
  if (compact) drawer.setAttribute("aria-modal", "true");
  else drawer.removeAttribute("aria-modal");
  drawer.setAttribute("aria-hidden", open ? "false" : "true");
  drawer.toggleAttribute("tabindex", compact);
  document.body.classList.toggle("job-center-open", open);
  document.body.classList.toggle("job-center-modal-open", open && compact);
  setJobBackgroundInert(open && compact);
  button.setAttribute("aria-expanded", String(open));
}

export function openJobCenter(trigger = document.activeElement) {
  const drawer = optional("jobCenterDrawer");
  if (!drawer) return false;
  jobViewCallbacks.closeGitDrawer({ restoreFocus: false });
  jobViewCallbacks.closeSidebar({ restoreFocus: false });
  jobCenterTrigger = trigger instanceof HTMLElement ? trigger : optional("jobCenterButton");
  drawer.classList.remove("hidden");
  syncJobCenterAccessibility();
  window.requestAnimationFrame(() => optional("jobCenterCloseButton")?.focus());
  return true;
}

export function closeJobCenter(options = {}) {
  const drawer = optional("jobCenterDrawer");
  if (!drawer || drawer.classList.contains("hidden")) {
    syncJobCenterAccessibility();
    return false;
  }
  drawer.classList.add("hidden");
  syncJobCenterAccessibility();
  if (options.restoreFocus !== false && jobCenterTrigger?.isConnected) {
    jobCenterTrigger.focus();
  }
  jobCenterTrigger = null;
  return true;
}

function openDrawer(open) {
  const button = optional("jobCenterButton");
  if (!button) return;
  if (open) {
    openJobCenter(button);
    return;
  }
  closeJobCenter();
}
/**
 * 작업 center 이벤트를 DOM 요소와 핸들러에 연결합니다.
 */
export function bindJobCenter() {
  optional("jobCenterButton")?.addEventListener("click", () => openDrawer(true));
  optional("jobCenterCloseButton")?.addEventListener("click", () => openDrawer(false));
  optional("jobCenterClearButton")?.addEventListener("click", () => {
    void clearCompleted();
  });
  for (const button of document.querySelectorAll("[data-job-filter]")) {
    button.addEventListener("click", () => {
      filter = button.dataset.jobFilter || "active";
      for (const item of document.querySelectorAll("[data-job-filter]")) {
        item.classList.toggle("active", item === button);
      }
      renderJobs();
    });
  }
  document.addEventListener("keydown", (event) => {
    if (!isJobCenterOpen() || !compactJobCenterActive()) return;
    trapFocusWithin(event, optional("jobCenterDrawer"));
  });
  window.matchMedia?.(COMPACT_SURFACE_QUERY).addEventListener("change", syncJobCenterAccessibility);
  syncJobCenterAccessibility();
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const cancelId = target.getAttribute("data-job-cancel");
    if (cancelId) void cancelJob(cancelId);
    const dismissId = target.getAttribute("data-job-dismiss");
    if (dismissId) void dismissJob(dismissId);
    const resultId = target.getAttribute("data-job-result");
    if (resultId) {
      const job = jobs.find((item) => item.jobId === resultId);
      if (!job) return;
      if (expandedJobIds.has(resultId)) {
        expandedJobIds.delete(resultId);
      } else {
        expandedJobIds.add(resultId);
      }
      renderJobs();
      optional(jobResultPanelId(job))?.focus({ preventScroll: true });
    }
    const failureAction = target.getAttribute("data-job-failure-action");
    const failureJobId = target.getAttribute("data-job-id");
    const detailIndex = Number.parseInt(target.getAttribute("data-detail-index") || "", 10);
    if (failureAction && failureJobId && Number.isInteger(detailIndex)) {
      const job = jobs.find((item) => item.jobId === failureJobId);
      const detail = job ? failureDetails(job)[detailIndex] : null;
      if (job && detail) {
        void jobViewCallbacks.openFailureTarget(detail, failureAction, job);
      }
    }
  });
  void refreshJobs();
}
