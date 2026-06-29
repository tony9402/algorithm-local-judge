/**
 * 작업 화면 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { api, normalizeErrorDetail } from "./api.js";
import { optional, escapeHtml } from "./dom.js";
import { showAlert } from "./feedback.js";
import { setProgressInsight, updateRunningProgressDetail } from "./progress.js";
import { reconcileRunAllLockWithJobs } from "./actions/build-locks.js";
import { updateGlobalActionState } from "./actions/build-status.js";

let jobs = [];
let filter = "active";
let pollTimer = null;
const waiters = new Map();

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
    failed: jobs.filter((job) => job.status === "failed").length,
  };
}

function visibleJobs() {
  if (filter === "active") return jobs.filter((job) => ACTIVE.has(job.status));
  if (filter === "failed") return jobs.filter((job) => job.status === "failed");
  return jobs.filter((job) => DONE.has(job.status));
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
    return `role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}" aria-label="${escapeHtml(statusLabel(job.status))}"`;
  }
  if (active && job.status !== "queued") {
    return `role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-label="${escapeHtml(statusLabel(job.status))}"`;
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
  const resultButton = job.status === "succeeded"
    ? `<button type="button" data-job-result="${escapeHtml(job.jobId)}">결과 보기</button>`
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
  return `
    <article class="job-row ${escapeHtml(job.status)}" data-job-id="${escapeHtml(job.jobId)}">
      <div class="job-row-header">
        <span class="job-row-title">
          <span class="job-status ${escapeHtml(job.status)}" aria-label="${escapeHtml(statusLabel(job.status))}">${escapeHtml(statusLabel(job.status))}</span>
          ${escapeHtml(job.title || job.kind)}
        </span>
        <span class="job-row-time">${escapeHtml(formatTime(job.startedAt || job.queuedAt))}</span>
      </div>
      <div class="job-row-subheader">
        <span class="job-row-target">${escapeHtml(formatTarget(job) || job.kind)}</span>
      </div>
      <div class="${escapeHtml(progressClass)}" ${progressAttrs}><span class="job-progress-fill" style="width:${visualPercent}%"></span></div>
      ${details ? `<div class="job-progress-meta">${escapeHtml(details)}</div>` : ""}
      <div class="job-row-log">${escapeHtml(job.lastLog || job.progress?.message || job.error || "")}</div>
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
    jobs = payload.jobs || [];
    if (reconcileRunAllLockWithJobs(jobs)) updateGlobalActionState();
    renderJobs();
    await resolveWaiters();
  } finally {
    schedulePoll();
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
  showAlert(`${job.title || options.label || "작업"}을 작업 센터에 추가했습니다.`, "info", {
    title: job.status === "queued" ? "작업 대기열" : "작업 시작",
    timeout: 3500,
  });
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
  showAlert(`${job.title || options.label || "작업"}을 작업 센터에 추가했습니다.`, "info", {
    title: job.status === "queued" ? "작업 대기열" : "작업 시작",
    timeout: 3500,
  });
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
  await api(`/api/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
  await refreshJobs();
}
/**
 * completed 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 */
async function clearCompleted() {
  await api("/api/jobs/completed", { method: "DELETE" });
  await refreshJobs();
}
/**
 * drawer 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 *
 * @param {boolean} open drawer을 계산하거나 검증할 때 필요한 open 입력입니다.
 */
function openDrawer(open) {
  const drawer = optional("jobCenterDrawer");
  const button = optional("jobCenterButton");
  if (!drawer || !button) return;
  drawer.classList.toggle("hidden", !open);
  button.setAttribute("aria-expanded", String(open));
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
      if (job?.result) {
        showAlert(job.lastLog || "작업 결과가 준비되었습니다.", "success", {
          title: job.title || "작업 완료",
          timeout: 4500,
        });
      }
    }
  });
  void refreshJobs();
}
