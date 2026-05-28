const app = window.AljApp;
const { state } = app;

let jobs = [];
let filter = "active";
let pollTimer = null;
const waiters = new Map();
const ACTIVE = new Set(["queued", "running", "cancelling"]);
const DONE = new Set(["succeeded", "cancelled", "stale"]);

/**
 * statusLabel 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} status `status` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function statusLabel(status) {
  return {
    queued: "Queued",
    running: "Running",
    cancelling: "Cancel requested",
    succeeded: "Done",
    failed: "Failed",
    cancelled: "Cancelled",
    stale: "Stale",
  }[status] || status;
}

/**
 * counts 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function counts() {
  return {
    active: jobs.filter((job) => ACTIVE.has(job.status)).length,
    running: jobs.filter((job) => job.status === "running" || job.status === "cancelling").length,
    queued: jobs.filter((job) => job.status === "queued").length,
    failed: jobs.filter((job) => job.status === "failed").length,
  };
}

/**
 * visibleJobs 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function visibleJobs() {
  if (filter === "active") return jobs.filter((job) => ACTIVE.has(job.status));
  if (filter === "failed") return jobs.filter((job) => job.status === "failed");
  return jobs.filter((job) => DONE.has(job.status));
}

/**
 * targetText 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} job `job` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function targetText(job) {
  const target = job.target || {};
  return [
    target.problemId || (job.problemId !== "__packs__" ? job.problemId : ""),
    target.profile,
    target.source,
    target.filename,
    target.repository,
    target.assetName,
  ].filter(Boolean).join(" · ");
}

/**
 * percent 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} job `job` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function percent(job) {
  const progress = job.progress || {};
  const current = Number(progress.current);
  const total = Number(progress.total);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

/**
 * timeLabel 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function timeLabel(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/**
 * renderSummary 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function renderSummary() {
  const value = counts();
  const button = app.optional("jobsButton");
  const meta = app.optional("jobsMeta");
  const text = value.active
    ? `Jobs ${value.active} · running ${value.running} · queued ${value.queued}`
    : value.failed
      ? `Jobs · failed ${value.failed}`
      : "Jobs 0";
  if (button) button.textContent = text;
  if (meta) {
    meta.textContent = value.active
      ? `${value.running} running, ${value.queued} queued`
      : value.failed
        ? `${value.failed} failed job(s)`
        : "No queued jobs.";
  }
}

/**
 * renderJobs 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function renderJobs() {
  renderSummary();
  const list = app.optional("jobsList");
  if (!list) return;
  const items = visibleJobs();
  list.classList.toggle("muted", !items.length);
  if (!items.length) {
    list.textContent = "No jobs.";
    return;
  }
  list.innerHTML = app.escapeHtml("") + items.map(renderJobRow).join("");
}

/**
 * renderJobRow 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} job `job` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function renderJobRow(job) {
  const progress = percent(job);
  const active = ["queued", "running", "cancelling"].includes(job.status);
  const blockedCancel = active && job.cancelMode === "blocked" && job.cancelBlockedReason;
  const canCancel = job.cancelSupported && ["queued", "running"].includes(job.status);
  const cancelling = job.status === "cancelling";
  const terminal = ["succeeded", "failed", "cancelled", "stale"].includes(job.status);
  const resultButton = job.status === "succeeded"
    ? `<button type="button" data-job-result="${app.escapeHtml(job.jobId)}">View Result</button>`
    : "";
  const cancelButton = canCancel || cancelling
    ? `<button type="button" data-job-cancel="${app.escapeHtml(job.jobId)}" ${cancelling ? "disabled" : ""}>${cancelling ? "Cancel requested" : "Cancel"}</button>`
    : blockedCancel
      ? `<button type="button" disabled title="${app.escapeHtml(job.cancelBlockedReason)}">Cancel unavailable</button>`
    : "";
  const cancelReason = job.cancelBlockedReason
    ? `<div class="job-cancel-reason">${app.escapeHtml(job.cancelBlockedReason)}</div>`
    : "";
  const dismissButton = terminal
    ? `<button type="button" data-job-dismiss="${app.escapeHtml(job.jobId)}">Dismiss</button>`
    : "";
  return `
    <article class="job-row" data-job-id="${app.escapeHtml(job.jobId)}">
      <div class="job-row-header">
        <span class="job-row-title">${app.escapeHtml(job.title || job.kind)}</span>
        <span class="job-status ${app.escapeHtml(job.status)}" aria-label="${app.escapeHtml(statusLabel(job.status))}">${app.escapeHtml(statusLabel(job.status))}</span>
      </div>
      <div class="job-row-target">${app.escapeHtml(targetText(job) || job.kind)}</div>
      <div class="job-progress-track" aria-hidden="true"><span class="job-progress-fill" style="width:${progress}%"></span></div>
      <div class="job-row-log">${app.escapeHtml(job.lastLog || job.error || job.progress?.message || "")}</div>
      ${cancelReason}
      <div class="job-row-time">${app.escapeHtml(timeLabel(job.startedAt || job.queuedAt))}</div>
      <div class="job-row-actions">${cancelButton}${resultButton}${dismissButton}</div>
    </article>
  `;
}

/**
 * refreshJobs 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
async function refreshJobs() {
  try {
    const payload = await app.api("/api/jobs");
    jobs = payload.jobs || [];
    renderJobs();
    resolveWaiters();
  } finally {
    scheduleJobsPoll();
  }
}

/**
 * scheduleJobsPoll 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} delay `delay` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function scheduleJobsPoll(delay = 900) {
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = window.setTimeout(refreshJobs, delay);
}

/**
 * resolveWaiters 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function resolveWaiters() {
  for (const [jobId, waiter] of waiters.entries()) {
    const job = jobs.find((item) => item.jobId === jobId);
    if (!job) continue;
    if (job.status === "succeeded") {
      waiters.delete(jobId);
      appendJobLogs(job);
      waiter.resolve(job);
    }
    if (["failed", "cancelled", "stale"].includes(job.status)) {
      waiters.delete(jobId);
      appendJobLogs(job);
      waiter.reject(new Error(job.error || statusLabel(job.status)));
    }
  }
}

/**
 * appendJobLogs 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} job `job` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function appendJobLogs(job) {
  /**
   * messages 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} job `job` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  const messages = (job.logs || []).map((entry) => entry.message).filter(Boolean);
  if (!messages.length && job.lastLog) messages.push(job.lastLog);
  for (const message of messages) {
    if (!state.debugLogs.includes(message)) state.debugLogs.push(message);
  }
  app.renderDebugLog?.();
}

/**
 * openJobs 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} open `open` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function openJobs(open = true) {
  const panel = app.optional("jobsPanel");
  const button = app.optional("jobsButton");
  if (!panel || !button) return;
  panel.classList.toggle("hidden", !open);
  button.setAttribute("aria-expanded", String(open));
}

/**
 * runQueuedJob 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function runQueuedJob(path, options = {}) {
  const job = await app.api(path, options);
  openJobs(true);
  app.showToast(`${job.title || "Job"} queued.`, "info");
  await refreshJobs();
  return new Promise((resolve, reject) => {
    waiters.set(job.jobId, {
      /**
       * resolve 함수를 실행하고 반환 값을 계산합니다.
       *
       * @param {any} finished `finished` 값입니다.
       * @returns {any} 처리 결과를 반환합니다.
       */
      resolve: (finished) => resolve(finished.result || {}),
      reject,
    });
    scheduleJobsPoll(250);
  });
}

/**
 * cancelJob 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} jobId `jobId` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function cancelJob(jobId) {
  await app.api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
  app.showToast("Cancel requested.", "info");
  await refreshJobs();
}

/**
 * dismissJob 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} jobId `jobId` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function dismissJob(jobId) {
  await app.api(`/api/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
  await refreshJobs();
}

/**
 * clearCompletedJobs 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
async function clearCompletedJobs() {
  await app.api("/api/jobs/completed", { method: "DELETE" });
  await refreshJobs();
}

/**
 * applyJobResult 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} jobId `jobId` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function applyJobResult(jobId) {
  const job = jobs.find((item) => item.jobId === jobId);
  if (!job?.result) return;
  if (job.kind === "judge-run") {
    await app.restoreRunResult(job.result);
    await app.refreshSecondaryData();
  } else if (job.kind === "judge-generate") {
    app.setStatusCard("data", "Generated", app.profileCaseText(job.result.caseCount, job.result.profile));
    app.setSummary(`${job.result.profile} test data ready: ${job.result.label}`, "result-summary success");
  } else if (job.kind?.startsWith("judge-pack")) {
    app.$("packStatus").textContent = app.installLabel(job.result);
    app.$("packStatus").className = "modal-status success";
    app.clearSampleCache();
    await app.refresh();
  }
}

/**
 * bindJobs 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function bindJobs() {
  app.on("jobsButton", "click", () => openJobs(app.optional("jobsPanel")?.classList.contains("hidden")));
  app.on("jobsClearButton", "click", () => app.withErrors(clearCompletedJobs));
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
    if (cancelId) void app.withErrors(() => cancelJob(cancelId));
    const dismissId = target.getAttribute("data-job-dismiss");
    if (dismissId) void app.withErrors(() => dismissJob(dismissId));
    const resultId = target.getAttribute("data-job-result");
    if (resultId) void app.withErrors(() => applyJobResult(resultId));
  });
  void refreshJobs();
}

Object.assign(app, {
  bindJobs,
  refreshJobs,
  runQueuedJob,
});
