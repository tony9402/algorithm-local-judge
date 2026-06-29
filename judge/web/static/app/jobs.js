/**
 * 작업 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;

let jobs = [];
let allJobs = [];
let pollTimer = null;
const waiters = new Map();
const ACTIVE = new Set(["queued", "running", "cancelling"]);
const DONE = new Set(["succeeded", "cancelled", "stale"]);

function statusLabel(status) {
  return {
    queued: "대기 중",
    running: "채점 중",
    cancelling: "취소 요청됨",
    succeeded: "완료",
    failed: "실패",
    cancelled: "취소됨",
    stale: "만료됨",
  }[status] || status;
}

function counts() {
  const source = allJobs.length ? allJobs : jobs;
  const runJobs = state.jobsServerPaged ? { length: state.jobsTotal } : source.filter((job) => job.kind === "judge-run");
  return {
    active: source.filter((job) => ACTIVE.has(job.status)).length,
    running: source.filter((job) => job.status === "running" || job.status === "cancelling").length,
    queued: source.filter((job) => job.status === "queued").length,
    failed: source.filter((job) => job.status === "failed").length,
    runs: runJobs.length,
  };
}

function visibleJobs() {
  if (state.jobsServerPaged) return jobs;
  const runJobs = jobs
    .filter((job) => job.kind === "judge-run")
    .sort((left, right) => String(right.queuedAt || "").localeCompare(String(left.queuedAt || "")));
  const totalPages = Math.max(1, Math.ceil(runJobs.length / state.jobsPageSize));
  state.jobsPage = Math.max(1, Math.min(state.jobsPage, totalPages));
  const start = (state.jobsPage - 1) * state.jobsPageSize;
  return runJobs.slice(start, start + state.jobsPageSize);
}

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

function percent(job) {
  const progress = job.progress || {};
  const current = Number(progress.current);
  const total = Number(progress.total);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

function timeLabel(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
/**
 * summary 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderSummary() {
  const value = counts();
  const button = app.optional("jobsButton");
  const meta = app.optional("jobsMeta");
  const text = value.active
    ? `작업 ${value.active} · 실행 ${value.running} · 대기 ${value.queued}`
    : value.failed
      ? `작업 · 실패 ${value.failed}`
      : `채점 결과 ${value.runs}`;
  if (button) button.textContent = text;
  if (meta) {
    meta.textContent = value.runs ? `제출 기록 ${value.runs}개` : "제출 기록이 없습니다.";
  }
}
/**
 * 작업 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderJobs() {
  renderSummary();
  const list = app.optional("jobsList");
  if (!list) return;
  const items = visibleJobs();
  const runCount = state.jobsServerPaged
    ? state.jobsTotal
    : jobs.filter((job) => job.kind === "judge-run").length;
  const totalPages = state.jobsServerPaged
    ? state.jobsTotalPages
    : Math.max(1, Math.ceil(runCount / state.jobsPageSize));
  app.setText("jobsPageLabel", `${state.jobsPage} / ${totalPages}`);
  app.setDisabled("jobsPrevButton", state.jobsPage <= 1);
  app.setDisabled("jobsNextButton", state.jobsPage >= totalPages);
  list.classList.toggle("muted", !items.length);
  if (!items.length) {
    list.textContent = "제출 기록이 없습니다.";
    return;
  }
  list.innerHTML = app.escapeHtml("") + items.map(renderJobRow).join("");
}
function renderJobRow(job) {
  const progress = percent(job);
  const active = ["queued", "running", "cancelling"].includes(job.status);
  const blockedCancel = active && job.cancelMode === "blocked" && job.cancelBlockedReason;
  const canCancel = job.cancelSupported && ["queued", "running"].includes(job.status);
  const cancelling = job.status === "cancelling";
  const terminal = ["succeeded", "failed", "cancelled", "stale"].includes(job.status);
  const resultButton = job.status === "succeeded"
    ? `<button type="button" data-job-result="${app.escapeHtml(job.jobId)}">채점 결과 보기</button>`
    : "";
  const cancelButton = canCancel || cancelling
    ? `<button type="button" data-job-cancel="${app.escapeHtml(job.jobId)}" ${cancelling ? "disabled" : ""}>${cancelling ? "취소 요청됨" : "취소"}</button>`
    : blockedCancel
      ? `<button type="button" disabled title="${app.escapeHtml(job.cancelBlockedReason)}">취소 불가</button>`
    : "";
  const cancelReason = job.cancelBlockedReason
    ? `<div class="job-cancel-reason">${app.escapeHtml(job.cancelBlockedReason)}</div>`
    : "";
  const dismissButton = terminal
    ? `<button type="button" data-job-dismiss="${app.escapeHtml(job.jobId)}">기록 삭제</button>`
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
 * 작업 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 */
async function refreshJobs() {
  try {
    const params = new URLSearchParams({
      kind: "judge-run",
      page: String(state.jobsPage),
      page_size: String(state.jobsPageSize),
      order: "queued_desc",
    });
    const payload = await app.api(`/api/jobs?${params.toString()}`);
    jobs = payload.jobs || [];
    if (Number.isFinite(payload.total)) {
      state.jobsServerPaged = true;
      state.jobsPage = payload.page || state.jobsPage;
      state.jobsPageSize = payload.pageSize || state.jobsPageSize;
      state.jobsTotal = payload.total;
      state.jobsTotalPages = payload.totalPages || 1;
    } else {
      state.jobsServerPaged = false;
      state.jobsTotal = jobs.filter((job) => job.kind === "judge-run").length;
      state.jobsTotalPages = Math.max(1, Math.ceil(state.jobsTotal / state.jobsPageSize));
    }
    allJobs = jobs;
    if (waiters.size > 0) {
      const allPayload = await app.api("/api/jobs?order=queued_desc&page=1&page_size=100");
      allJobs = allPayload.jobs || jobs;
    }
    renderJobs();
    resolveWaiters();
  } finally {
    scheduleJobsPoll();
  }
}

function scheduleJobsPoll(delay = 900) {
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = window.setTimeout(refreshJobs, delay);
}

function resolveWaiters() {
  for (const [jobId, waiter] of waiters.entries()) {
    const source = allJobs.length ? allJobs : jobs;
    const job = source.find((item) => item.jobId === jobId);
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
function appendJobLogs(job) {
  const messages = (job.logs || []).map((entry) => entry.message).filter(Boolean);
  if (!messages.length && job.lastLog) messages.push(job.lastLog);
  for (const message of messages) {
    if (!state.debugLogs.includes(message)) state.debugLogs.push(message);
  }
  app.renderDebugLog?.();
}
/**
 * 작업 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 *
 * @param {boolean} open 작업을 계산하거나 검증할 때 필요한 open 입력입니다.
 */
function openJobs(open = true) {
  const panel = app.optional("jobsPanel");
  const button = app.optional("jobsButton");
  if (!panel || !button) return;
  panel.classList.toggle("hidden", !open);
  button.setAttribute("aria-expanded", String(open));
}
async function runQueuedJob(path, options = {}) {
  const { onQueued, ...requestOptions } = options;
  const job = await app.api(path, requestOptions);
  openJobs(true);
  if (typeof onQueued === "function") onQueued(job);
  app.showToast(`${job.title || "작업"} 대기열에 추가됨`, "info");
  await refreshJobs();
  return new Promise((resolve, reject) => {
    waiters.set(job.jobId, {
      resolve: (finished) => resolve(finished.result || {}),
      reject,
    });
    scheduleJobsPoll(250);
  });
}
async function cancelJob(jobId) {
  await app.api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
  app.showToast("취소를 요청했습니다.", "info");
  await refreshJobs();
}
async function dismissJob(jobId) {
  await app.api(`/api/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
  await refreshJobs();
}
/**
 * completed 작업 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 */
async function clearCompletedJobs() {
  await app.api("/api/jobs/completed", { method: "DELETE" });
  await refreshJobs();
}

async function applyJobResult(jobId) {
  const job = jobs.find((item) => item.jobId === jobId);
  if (!job?.result) return;
  if (job.kind === "judge-run") {
    await app.restoreRunResult(job.result);
    app.showResultModal(job.result);
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
 * 작업 이벤트를 DOM 요소와 핸들러에 연결합니다.
 */
function bindJobs() {
  app.on("jobsButton", "click", () => openJobs(app.optional("jobsPanel")?.classList.contains("hidden")));
  app.on("jobsClearButton", "click", () => app.withErrors(clearCompletedJobs));
  app.on("jobsPrevButton", "click", () => app.withErrors(async () => {
    state.jobsPage = Math.max(1, state.jobsPage - 1);
    await refreshJobs();
  }));
  app.on("jobsNextButton", "click", () => app.withErrors(async () => {
    state.jobsPage += 1;
    await refreshJobs();
  }));
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
