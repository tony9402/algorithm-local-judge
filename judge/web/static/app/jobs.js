/**
 * 작업 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;

let jobs = [];
let allJobs = [];
let pollTimer = null;
const waiters = new Map();
const jobStatuses = new Map();
const announcedTerminalJobs = new Set();
let jobsPanelHome = null;
const ACTIVE = new Set(["queued", "running", "cancelling"]);
const TERMINAL = new Set(["succeeded", "failed", "cancelled", "stale"]);
const JOBS_COMPACT_QUERY = "(max-width: 720px)";

function verdictLabel(status) {
  return {
    accepted: "맞았습니다",
    wrong_answer: "오답",
    compile_error: "컴파일 오류",
    runtime_error: "런타임 오류",
    time_limit: "시간 초과",
    memory_limit: "메모리 초과",
  }[status] || (status ? `알 수 없는 판정 (${status})` : "결과 없음");
}

function statusLabel(status) {
  return {
    queued: "대기 중",
    running: "실행 중",
    cancelling: "취소 요청됨",
    succeeded: "완료",
    failed: "실패",
    cancelled: "취소됨",
    stale: "만료됨",
  }[status] || (status ? `알 수 없는 상태 (${status})` : "상태 없음");
}

function outcomeLabel(outcome) {
  return {
    pending: "진행 중",
    passed: "성공",
    failed: "주의 필요",
    cancelled: "취소됨",
    stale: "만료됨",
  }[outcome] || (outcome ? `알 수 없는 결과 (${outcome})` : "");
}

function jobOutcome(job) {
  if (job.outcome) return job.outcome;
  if (ACTIVE.has(job.status)) return "pending";
  if (job.status === "failed") return "failed";
  if (job.status === "cancelled") return "cancelled";
  if (job.status === "stale") return "stale";
  if (job.kind === "judge-cases-compile" && job.result?.valid === false) return "failed";
  if (job.kind === "judge-run" && job.result?.status && job.result.status !== "accepted") return "failed";
  if (job.result?.passed === false || job.failureDetails?.length || job.result?.failureDetails?.length) {
    return "failed";
  }
  if (job.status === "succeeded") return "passed";
  return job.status || "unknown";
}

function jobNeedsAttention(job) {
  return jobOutcome(job) === "failed" || job.status === "failed";
}

function displayStatus(job) {
  if (job.kind === "judge-run" && job.result?.status) return verdictLabel(job.result.status);
  if (jobNeedsAttention(job)) return outcomeLabel("failed");
  return statusLabel(job.status);
}

function displayKind(job) {
  if (job.kind === "judge-run") return "채점";
  if (job.kind === "judge-cases-compile") return "cases.yml 검사";
  if (job.kind === "judge-generate") return "데이터 생성";
  if (job.kind?.startsWith("judge-pack")) return "문제 팩";
  return job.kind || "작업";
}

function isMaintenanceJob(job) {
  return job.kind === "judge-generate"
    || job.kind === "judge-cases-compile"
    || job.kind?.startsWith("judge-pack");
}

function counts() {
  const source = allJobs.length ? allJobs : jobs;
  return {
    total: source.length,
    active: source.filter((job) => ACTIVE.has(job.status)).length,
    running: source.filter((job) => job.status === "running" || job.status === "cancelling").length,
    queued: source.filter((job) => job.status === "queued").length,
    attention: source.filter(jobNeedsAttention).length,
    runs: source.filter((job) => job.kind === "judge-run").length,
    maintenance: source.filter(isMaintenanceJob).length,
  };
}

function jobMatchesFilter(job) {
  const filter = state.jobsFilter || "all";
  if (filter === "active") return ACTIVE.has(job.status);
  if (filter === "attention") return jobNeedsAttention(job);
  if (filter === "runs") return job.kind === "judge-run";
  if (filter === "maintenance") return isMaintenanceJob(job);
  return true;
}

function filteredJobs() {
  const source = allJobs.length ? allJobs : jobs;
  return source
    .filter(jobMatchesFilter)
    .sort((left, right) => String(right.queuedAt || "").localeCompare(String(left.queuedAt || "")));
}

function visibleJobs() {
  const filtered = filteredJobs();
  const totalPages = Math.max(1, Math.ceil(filtered.length / state.jobsPageSize));
  state.jobsPage = Math.max(1, Math.min(state.jobsPage, totalPages));
  state.jobsTotal = filtered.length;
  state.jobsTotalPages = totalPages;
  const start = (state.jobsPage - 1) * state.jobsPageSize;
  return filtered.slice(start, start + state.jobsPageSize);
}

function targetText(job) {
  const target = job.target || {};
  return [
    target.problemId || (job.problemId !== "__packs__" ? job.problemId : ""),
    target.profile ? app.profileLabel(target.profile) : "",
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
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) {
    if (ACTIVE.has(job.status)) return 12;
    return TERMINAL.has(job.status) ? 100 : 0;
  }
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

function timeLabel(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function failureDetails(job) {
  if (Array.isArray(job.failureDetails) && job.failureDetails.length) return job.failureDetails;
  if (Array.isArray(job.result?.failureDetails) && job.result.failureDetails.length) {
    return job.result.failureDetails;
  }
  if (job.kind === "judge-cases-compile" && job.result?.valid === false) {
    const first = job.result.diagnostics?.[0] || {};
    return [{
      label: "cases.yml 검사",
      target: [first.path, first.line ? `${first.line}번째 줄` : "", first.location].filter(Boolean).join(" · "),
      message: first.message || "cases.yml 검사에 실패했습니다.",
      profile: first.profile,
      line: first.line,
    }];
  }
  if (job.kind === "judge-run" && job.result?.status && job.result.status !== "accepted") {
    const first = (job.result.cases || []).find((item) => item.status && item.status !== "ok") || {};
    return [{
      label: app.verdictLabel(job.result.status),
      target: first.case ? `테스트케이스 ${first.case}` : targetText(job),
      message: first.message || `${app.verdictLabel(job.result.status)} 결과입니다.`,
      status: job.result.status,
      profile: job.result.profile,
    }];
  }
  if (job.error) {
    return [{ label: job.failureStageLabel || displayKind(job), target: targetText(job), message: job.error }];
  }
  return [];
}

function renderFailureDetails(job) {
  const details = failureDetails(job);
  if (!details.length && !jobNeedsAttention(job)) return "";
  const stage = job.failureStageLabel || job.result?.failureStageLabel || job.progress?.label || displayKind(job);
  const items = details.length
    ? details.map((detail) => {
      const label = detail.label || stage;
      const target = detail.target || detail.case || detail.location || detail.problemId || "";
      const message = detail.message || job.error || job.lastLog || "확인할 실패 결과가 있습니다.";
      const meta = [
        detail.profile ? `프로필 ${app.profileLabel(detail.profile)}` : "",
        detail.line ? `${detail.line}번째 줄` : "",
        detail.status ? verdictLabel(detail.status) : "",
      ].filter(Boolean).join(" · ");
      return `
        <li>
          <strong>${app.escapeHtml(label)}</strong>
          ${target ? `<span>${app.escapeHtml(target)}</span>` : ""}
          <p>${app.escapeHtml(message)}</p>
          ${meta ? `<small>${app.escapeHtml(meta)}</small>` : ""}
        </li>
      `;
    }).join("")
    : `<li><strong>${app.escapeHtml(stage)}</strong><p>${app.escapeHtml(job.error || job.lastLog || "작업 결과를 확인하세요.")}</p></li>`;
  return `
    <div class="job-failure">
      <div class="job-failure-title">${app.escapeHtml(stage)}</div>
      <ul>${items}</ul>
    </div>
  `;
}

function renderJobLogs(job) {
  const logs = (job.logs || []).map((entry) => entry.message).filter(Boolean);
  if (!logs.length && job.lastLog) logs.push(job.lastLog);
  if (!logs.length) return "";
  const items = logs.slice(-8).map((message) => `<li>${app.escapeHtml(message)}</li>`).join("");
  return `
    <details class="job-log-list">
      <summary>최근 로그 ${logs.length}개</summary>
      <ul>${items}</ul>
    </details>
  `;
}

/**
 * summary 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderSummary() {
  const value = counts();
  const button = app.optional("jobsButton");
  const meta = app.optional("jobsMeta");
  const label = value.attention
    ? `작업 센터 · 주의 ${value.attention}`
    : value.active
      ? `작업 센터 · 진행 ${value.active}`
      : `작업 센터 ${value.total}`;
  if (button) button.textContent = label;
  if (meta) {
    meta.textContent = value.total
      ? `전체 ${value.total}개 · 진행 ${value.active}개 · 주의 ${value.attention}개`
      : "아직 기록된 작업이 없습니다.";
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
  app.setText("jobsPageLabel", `${state.jobsPage} / ${state.jobsTotalPages}`);
  app.setDisabled("jobsPrevButton", state.jobsPage <= 1);
  app.setDisabled("jobsNextButton", state.jobsPage >= state.jobsTotalPages);
  for (const button of document.querySelectorAll("[data-jobs-filter]")) {
    const active = button.getAttribute("data-jobs-filter") === (state.jobsFilter || "all");
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  list.classList.toggle("muted", !items.length);
  if (!items.length) {
    list.textContent = state.jobsFilter === "all" ? "아직 작업 기록이 없습니다." : "이 필터에 맞는 작업이 없습니다.";
    return;
  }
  list.innerHTML = app.escapeHtml("") + items.map(renderJobRow).join("");
}

function renderJobRow(job) {
  const progress = percent(job);
  const active = ACTIVE.has(job.status);
  const blockedCancel = active && job.cancelMode === "blocked" && job.cancelBlockedReason;
  const canCancel = job.cancelSupported && ["queued", "running"].includes(job.status);
  const cancelling = job.status === "cancelling";
  const terminal = TERMINAL.has(job.status);
  const outcome = jobOutcome(job);
  const resultButton = job.status === "succeeded" && job.result
    ? `<button type="button" data-job-result="${app.escapeHtml(job.jobId)}">결과 보기</button>`
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
    <article class="job-row ${jobNeedsAttention(job) ? "attention" : ""}" data-job-id="${app.escapeHtml(job.jobId)}">
      <div class="job-row-header">
        <div>
          <span class="job-row-title">${app.escapeHtml(job.title || displayKind(job))}</span>
          <span class="job-row-kind">${app.escapeHtml(displayKind(job))}</span>
        </div>
        <div class="job-badges">
          <span class="job-status ${app.escapeHtml(job.status)}" aria-label="${app.escapeHtml(statusLabel(job.status))}">${app.escapeHtml(statusLabel(job.status))}</span>
          <span class="job-outcome ${app.escapeHtml(outcome)}">${app.escapeHtml(displayStatus(job))}</span>
        </div>
      </div>
      <div class="job-row-target">${app.escapeHtml(targetText(job) || displayKind(job))}</div>
      <div
        class="job-progress-track"
        role="progressbar"
        aria-label="${app.escapeHtml(job.title || displayKind(job))} 진행률"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow="${progress}"
      ><span class="job-progress-fill" style="width:${progress}%"></span></div>
      <div class="job-row-log">${app.escapeHtml(job.lastLog || job.error || job.progress?.message || "")}</div>
      ${renderFailureDetails(job)}
      ${renderJobLogs(job)}
      ${cancelReason}
      <div class="job-row-footer">
        <span class="job-row-time">${app.escapeHtml(timeLabel(job.startedAt || job.queuedAt))}</span>
        <div class="job-row-actions">${cancelButton}${resultButton}${dismissButton}</div>
      </div>
    </article>
  `;
}

function trackJobTransitions(nextJobs) {
  const announcements = [];
  for (const job of nextJobs) {
    const previous = jobStatuses.get(job.jobId);
    if (
      previous
      && !TERMINAL.has(previous)
      && TERMINAL.has(job.status)
      && !announcedTerminalJobs.has(job.jobId)
    ) {
      announcedTerminalJobs.add(job.jobId);
      announcements.push(
        `${job.title || displayKind(job)} 작업이 ${displayStatus(job)} 상태로 끝났습니다.`
      );
    }
    jobStatuses.set(job.jobId, job.status);
  }
  if (announcements.length) app.setText("jobsAnnouncements", announcements.join(" "));
}

/**
 * 작업 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 */
async function refreshJobs() {
  try {
    const payload = await app.api("/api/jobs?order=queued_desc&page=1&page_size=100");
    const nextJobs = payload.jobs || [];
    trackJobTransitions(nextJobs);
    jobs = nextJobs;
    allJobs = jobs;
    state.jobsServerPaged = false;
    renderJobs();
    app.renderPackJobProgress?.(jobs);
    resolveWaiters();
  } finally {
    scheduleJobsPoll();
  }
}

function scheduleJobsPoll(delay = 900) {
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = window.setTimeout(refreshJobs, delay);
}

function waitErrorMessage(job) {
  const detail = failureDetails(job)[0];
  return detail?.message || job.error || statusLabel(job.status);
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
      waiter.reject(new Error(waitErrorMessage(job)));
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
function jobsAreCompact() {
  return window.matchMedia(JOBS_COMPACT_QUERY).matches;
}

function syncJobsSemantics() {
  const panel = app.optional("jobsPanel");
  const button = app.optional("jobsButton");
  if (!panel || !button) return;
  if (jobsAreCompact()) {
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    button.setAttribute("aria-haspopup", "dialog");
  } else {
    panel.setAttribute("role", "complementary");
    panel.removeAttribute("aria-modal");
    button.removeAttribute("aria-haspopup");
  }
}

function setJobsClosed() {
  const panel = app.optional("jobsPanel");
  const button = app.optional("jobsButton");
  if (!panel || !button) return;
  panel.classList.add("hidden");
  document.body.classList.remove("jobs-open");
  button.setAttribute("aria-expanded", "false");
}

function moveJobsPanelToOverlayRoot() {
  const panel = app.optional("jobsPanel");
  if (!panel) return;
  if (!jobsPanelHome) {
    jobsPanelHome = { parent: panel.parentNode, nextSibling: panel.nextSibling };
  }
  document.body.appendChild(panel);
}

function restoreJobsPanelHome() {
  const panel = app.optional("jobsPanel");
  if (!panel || !jobsPanelHome?.parent) return;
  jobsPanelHome.parent.insertBefore(panel, jobsPanelHome.nextSibling);
}

function onJobsOverlayClosed() {
  setJobsClosed();
  restoreJobsPanelHome();
  syncJobsSemantics();
}

function closeJobsForOverlay() {
  if (app.optional("jobsPanel")?.classList.contains("hidden")) return;
  setJobsClosed();
  restoreJobsPanelHome();
}

function openJobs(open = true) {
  const panel = app.optional("jobsPanel");
  const button = app.optional("jobsButton");
  if (!panel || !button) return;
  syncJobsSemantics();
  if (!open) {
    if (jobsAreCompact() && panel.getAttribute("role") === "dialog" && app.hasActiveModal?.()) {
      app.closeModals();
    } else {
      setJobsClosed();
      button.focus();
    }
    return;
  }
  if (jobsAreCompact()) {
    button.setAttribute("aria-expanded", "true");
    document.body.classList.add("jobs-open");
    moveJobsPanelToOverlayRoot();
    app.openModal("jobsPanel");
    return;
  }
  restoreJobsPanelHome();
  if (app.hasActiveModal?.()) return;
  panel.classList.toggle("hidden", !open);
  document.body.classList.toggle("jobs-open", open);
  button.setAttribute("aria-expanded", String(open));
}

function setJobsFilter(filter) {
  state.jobsFilter = filter || "all";
  state.jobsPage = 1;
  renderJobs();
}

async function runQueuedJob(path, options = {}) {
  const { onQueued, ...requestOptions } = options;
  state.pendingJobAction = true;
  app.updateActionState?.();
  app.updatePackActionState?.();
  try {
    const job = await app.api(path, requestOptions);
    trackJobTransitions([job]);
    if (typeof onQueued === "function") onQueued(job);
    app.showToast(`${job.title || "작업"} 대기열에 추가됨`, "info");
    await refreshJobs();
    return await new Promise((resolve, reject) => {
      waiters.set(job.jobId, {
        resolve: (finished) => resolve(finished.result || {}),
        reject,
      });
      scheduleJobsPoll(250);
    });
  } finally {
    state.pendingJobAction = false;
    app.updateActionState?.();
    app.updatePackActionState?.();
  }
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
  const source = allJobs.length ? allJobs : jobs;
  const job = source.find((item) => item.jobId === jobId);
  if (!job?.result) return;
  if (job.kind === "judge-run") {
    await app.restoreRunResult(job.result);
    app.showResultModal(job.result);
    await app.refreshSecondaryData();
  } else if (job.kind === "judge-generate") {
    app.setStatusCard("data", "생성 완료", app.profileCaseText(job.result.caseCount, job.result.profile));
    app.setSummary(`${app.profileLabel(job.result.profile)} 테스트 데이터 준비 완료: ${job.result.label}`, "result-summary success");
  } else if (job.kind === "judge-cases-compile") {
    app.renderCasesCompileResult?.(job.result);
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
  syncJobsSemantics();
  app.on("jobsButton", "click", () => openJobs(app.optional("jobsPanel")?.classList.contains("hidden")));
  app.on("jobsCloseButton", "click", () => openJobs(false));
  app.on("jobsClearButton", "click", () => app.withErrors(clearCompletedJobs));
  app.on("jobsPrevButton", "click", () => app.withErrors(async () => {
    state.jobsPage = Math.max(1, state.jobsPage - 1);
    await refreshJobs();
  }));
  app.on("jobsNextButton", "click", () => app.withErrors(async () => {
    state.jobsPage += 1;
    await refreshJobs();
  }));
  for (const button of document.querySelectorAll("[data-jobs-filter]")) {
    button.addEventListener("click", () => setJobsFilter(button.getAttribute("data-jobs-filter") || "all"));
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
  document.addEventListener("keydown", (event) => {
    if (
      event.key === "Escape"
      && !event.defaultPrevented
      && !jobsAreCompact()
      && !app.optional("jobsPanel")?.classList.contains("hidden")
    ) {
      event.preventDefault();
      openJobs(false);
    }
  });
  window.matchMedia(JOBS_COMPACT_QUERY).addEventListener("change", () => {
    if (!app.optional("jobsPanel")?.classList.contains("hidden")) {
      if (app.hasActiveModal?.()) app.closeModals();
      else closeJobsForOverlay();
    }
    syncJobsSemantics();
  });
  void refreshJobs();
}

Object.assign(app, {
  bindJobs,
  closeJobsForOverlay,
  onJobsOverlayClosed,
  openJobs,
  refreshJobs,
  runQueuedJob,
  verdictLabel,
});
