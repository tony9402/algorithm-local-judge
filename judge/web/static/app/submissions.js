/** 제출한 소스와 채점 결과를 독립된 기록 화면으로 표시합니다. */

const app = window.AljApp;
const { state } = app;

const ACTIVE_LIFECYCLES = new Set(["queued", "running", "cancelling"]);
const LANGUAGE_META = {
  cpp: { label: "C++", className: "cpp" },
  c: { label: "C", className: "c" },
  python: { label: "Python", className: "python" },
  pypy: { label: "PyPy", className: "pypy" },
  java: { label: "Java", className: "java" },
};
let submissionPollTimer = null;
let queryTimer = null;

function normalizedLanguage(language) {
  const value = String(language || "").trim().toLowerCase();
  if (value === "c++" || value === "cc" || value === "cxx") return "cpp";
  return value;
}

function submissionLanguageMeta(submission) {
  const raw = submission?.language || submission?.languageId || "";
  const key = normalizedLanguage(raw);
  return {
    raw,
    label: LANGUAGE_META[key]?.label || raw || "언어 없음",
    className: LANGUAGE_META[key]?.className || "other",
  };
}

function profileLabel(profile) {
  return {
    full: "전체",
    sample: "샘플",
    hidden: "숨김",
  }[profile] || profile || "프로필 없음";
}

function submissionVerdict(submission) {
  return submission?.verdict || submission?.status || submission?.result?.status || "";
}

function lifecycleLabel(lifecycle) {
  return {
    queued: "대기 중",
    running: "채점 중",
    cancelling: "취소 요청됨",
    succeeded: "완료",
    completed: "완료",
    failed: "시스템 오류",
    cancelled: "취소됨",
    interrupted: "실행 중단됨",
    stale: "상세 만료됨",
  }[lifecycle] || lifecycle || "결과 없음";
}

function submissionStatusLabel(submission) {
  const verdict = submissionVerdict(submission);
  if (verdict) return app.verdictLabel(verdict);
  return lifecycleLabel(submission?.lifecycle);
}

function submissionStatusClass(submission) {
  const verdict = submissionVerdict(submission);
  if (verdict) return app.statusClassName(verdict);
  if (ACTIVE_LIFECYCLES.has(submission?.lifecycle)) return "neutral";
  if (["failed", "cancelled", "interrupted"].includes(submission?.lifecycle)) return "wrong";
  return "neutral";
}

function formatSubmissionTime(value) {
  if (!value) return "시각 확인 불가";
  const numeric = Number(value);
  const date = Number.isFinite(numeric)
    ? new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric)
    : new Date(value);
  return Number.isNaN(date.getTime()) ? "시각 확인 불가" : date.toLocaleString("ko-KR");
}

function submissionMeta(submission) {
  return [
    submission.problemId,
    profileLabel(submission.profile),
    submission.filename,
  ].filter(Boolean).join(" · ");
}

function metricsFor(submission) {
  const summary = submission?.resultSummary || {};
  const result = submission?.result || {};
  return result.metrics || summary.metrics || summary || {};
}

function metricLabel(metrics, labelKey, valueKey, suffix) {
  if (metrics?.[labelKey]) return metrics[labelKey];
  if (Number.isFinite(metrics?.[valueKey])) return `${metrics[valueKey]} ${suffix}`;
  return "확인 불가";
}

function submissionListItem(submission, compact = false) {
  const id = app.escapeHtml(submission.submissionId || "");
  const active = state.selectedSubmissionId === submission.submissionId;
  const metrics = metricsFor(submission);
  const time = metricLabel(metrics, "maxTimeLabel", "maxTimeMs", "ms");
  const memory = metricLabel(metrics, "maxMemoryLabel", "maxMemoryBytes", "B");
  const timestamp = formatSubmissionTime(submission.submittedAt || submission.createdAt);
  const language = submissionLanguageMeta(submission);
  const languageTitle = language.raw && language.raw !== language.label
    ? `제출 언어: ${language.label} (${language.raw})`
    : `제출 언어: ${language.label}`;
  return `
    <button
      type="button"
      class="submission-list-item ${active ? "active" : ""} ${compact ? "compact" : ""}"
      data-submission-id="${id}"
      aria-current="${active ? "true" : "false"}"
    >
      <span class="submission-list-primary">
        <strong class="submission-verdict ${app.escapeHtml(submissionStatusClass(submission))}">${app.escapeHtml(submissionStatusLabel(submission))}</strong>
        <span>${app.escapeHtml(submission.problemId || "문제 미상")}</span>
        <span class="submission-language language-${app.escapeHtml(language.className)}" aria-label="${app.escapeHtml(languageTitle)}" title="${app.escapeHtml(languageTitle)}">${app.escapeHtml(language.label)}</span>
        <time>${app.escapeHtml(timestamp)}</time>
      </span>
      <span class="submission-list-meta">${app.escapeHtml(submissionMeta(submission) || "제출 정보 없음")}</span>
      ${compact ? "" : `<span class="submission-list-metrics">최대 시간 ${app.escapeHtml(time)} · 최대 메모리 ${app.escapeHtml(memory)}</span>`}
    </button>
  `;
}

function activeFilters() {
  return {
    status: app.optional("submissionsStatusFilter")?.value || "",
    language: app.optional("submissionsLanguageFilter")?.value || "",
    profile: app.optional("submissionsProfileFilter")?.value || "",
    query: app.optional("submissionsQueryInput")?.value.trim() || "",
    order: app.optional("submissionsOrderSelect")?.value || "newest",
  };
}

function submissionsUrl({ recent = false } = {}) {
  const params = new URLSearchParams();
  params.set("page", "1");
  params.set("page_size", String(recent ? 3 : state.submissionsPageSize));
  if (!recent) params.set("page", String(state.submissionsPage));
  const scope = recent ? "problem" : state.submissionsScope;
  if (scope === "problem" && state.selectedProblem) params.set("problem_id", state.selectedProblem);
  if (!recent) {
    for (const [key, value] of Object.entries(activeFilters())) {
      if (value) params.set(key, value);
    }
  } else {
    params.set("order", "newest");
  }
  return `/api/submissions?${params.toString()}`;
}

function renderRecentSubmissions(submissions) {
  const list = app.optional("recentSubmissionsList");
  if (!list) return;
  list.classList.toggle("muted", !submissions.length);
  list.innerHTML = app.escapeHtml("") + (submissions.length
    ? submissions.map((submission) => submissionListItem(submission, true)).join("")
    : "아직 이 문제에 제출한 코드가 없습니다.");
}

async function refreshRecentSubmissions() {
  if (!state.selectedProblem) {
    renderRecentSubmissions([]);
    return;
  }
  try {
    const payload = await app.api(submissionsUrl({ recent: true }));
    renderRecentSubmissions(payload.submissions || []);
  } catch (error) {
    const list = app.optional("recentSubmissionsList");
    if (list) {
      list.classList.add("muted");
      list.innerHTML = `<span>최근 제출을 불러오지 못했습니다.</span><button type="button" data-submissions-retry="recent">다시 시도</button>`;
    }
  }
}

function setScopeButtons() {
  const problem = state.submissionsScope === "problem";
  const problemButton = app.optional("submissionsProblemScopeButton");
  const allButton = app.optional("submissionsAllScopeButton");
  problemButton?.classList.toggle("active", problem);
  allButton?.classList.toggle("active", !problem);
  problemButton?.setAttribute("aria-pressed", String(problem));
  allButton?.setAttribute("aria-pressed", String(!problem));
}

function renderSubmissions(payload) {
  const list = app.optional("submissionsList");
  if (!list) return;
  const submissions = payload.submissions || [];
  state.submissions = submissions;
  state.submissionsTotalPages = Math.max(1, Number(payload.totalPages) || 1);
  state.submissionsPage = Math.max(1, Number(payload.page) || state.submissionsPage);
  app.setText("submissionsCount", `${Number(payload.total) || 0}개 제출`);
  app.setText("submissionsPageLabel", `${state.submissionsPage} / ${state.submissionsTotalPages}`);
  app.setDisabled("submissionsPrevButton", state.submissionsPage <= 1);
  app.setDisabled("submissionsNextButton", state.submissionsPage >= state.submissionsTotalPages);
  const clearAllButton = app.optional("submissionsClearAllButton");
  const clearAllHint = app.optional("submissionsClearAllHint");
  if (clearAllButton) {
    clearAllButton.disabled = state.hasActiveSubmissions || !state.hasAnySubmissions;
    clearAllButton.title = state.hasActiveSubmissions
      ? "대기 중이거나 실행 중인 제출이 있어 전체 삭제할 수 없습니다."
      : "모든 제출 기록과 보존된 소스를 삭제합니다.";
  }
  if (clearAllHint) {
    clearAllHint.textContent = state.hasActiveSubmissions
      ? "대기 중이거나 실행 중인 제출이 있습니다. 완료 또는 취소된 뒤 전체 삭제할 수 있습니다."
      : "전체 삭제는 제출 기록과 보존된 소스를 지우며, 이전 캐시 코드 기록은 유지합니다.";
  }
  setScopeButtons();
  list.classList.toggle("muted", !submissions.length);
  if (!submissions.length) {
    const filters = activeFilters();
    const hasFilter = Boolean(filters.status || filters.language || filters.profile || filters.query);
    list.innerHTML = app.escapeHtml("") + (hasFilter
      ? '<div class="submissions-empty"><strong>필터와 일치하는 제출이 없습니다.</strong><button type="button" data-submissions-reset>필터 초기화</button></div>'
      : `<div class="submissions-empty"><strong>${state.submissionsScope === "problem" ? "이 문제의 제출 기록이 없습니다." : "아직 제출한 코드가 없습니다."}</strong><span>코드를 채점하면 제출과 결과가 여기에 표시됩니다.</span></div>`);
    clearSubmissionDetail();
    return;
  }
  list.innerHTML = app.escapeHtml("")
    + submissions.map((submission) => submissionListItem(submission)).join("");
  if (!submissions.some((item) => item.submissionId === state.selectedSubmissionId)) {
    void selectSubmission(submissions[0].submissionId, { moveFocus: false });
  }
}

function scheduleSubmissionPoll(submissions) {
  if (submissionPollTimer) window.clearTimeout(submissionPollTimer);
  submissionPollTimer = null;
  const drawerOpen = !app.optional("submissionsDrawer")?.classList.contains("hidden");
  if (
    drawerOpen
    && (state.hasActiveSubmissions || submissions.some((item) => ACTIVE_LIFECYCLES.has(item.lifecycle)))
  ) {
    submissionPollTimer = window.setTimeout(() => void refreshSubmissions(), 1000);
  }
}

async function refreshSubmissions() {
  if (state.submissionsScope === "problem" && !state.selectedProblem) {
    renderSubmissions({ submissions: [], page: 1, total: 0, totalPages: 1 });
    return;
  }
  const token = ++state.submissionsListToken;
  const list = app.optional("submissionsList");
  try {
    const [payload, all, queued, running] = await Promise.all([
      app.api(submissionsUrl()),
      app.api("/api/submissions?page=1&page_size=1"),
      app.api("/api/submissions?page=1&page_size=1&status=queued"),
      app.api("/api/submissions?page=1&page_size=1&status=running"),
    ]);
    if (token !== state.submissionsListToken) return;
    state.hasAnySubmissions = Number(all.total) > 0;
    state.hasActiveSubmissions = Number(queued.total) > 0 || Number(running.total) > 0;
    const selectedBefore = state.selectedSubmission;
    renderSubmissions(payload);
    const selectedAfter = (payload.submissions || []).find(
      (item) => item.submissionId === selectedBefore?.submissionId
    );
    if (
      selectedAfter
      && (
        selectedAfter.lifecycle !== selectedBefore.lifecycle
        || submissionVerdict(selectedAfter) !== submissionVerdict(selectedBefore)
      )
    ) {
      await selectSubmission(selectedAfter.submissionId, { moveFocus: false });
    }
    scheduleSubmissionPoll(payload.submissions || []);
  } catch (error) {
    if (token !== state.submissionsListToken || !list) return;
    list.classList.add("muted");
    list.innerHTML = `<div class="submissions-empty"><strong>제출 기록을 불러오지 못했습니다.</strong><span>${app.escapeHtml(error.message)}</span><button type="button" data-submissions-retry="list">다시 시도</button></div>`;
  }
}

function clearSubmissionDetail() {
  state.selectedSubmissionId = null;
  state.selectedSubmission = null;
  state.submissionDetailToken += 1;
  app.optional("submissionDetailEmpty")?.classList.remove("hidden");
  app.optional("submissionDetailContent")?.classList.add("hidden");
  app.optional("submissionsDrawer")?.classList.remove("has-detail");
}

function setSubmissionTab(tab) {
  state.submissionDetailTab = ["result", "cases", "source", "diagnostics"].includes(tab)
    ? tab
    : "result";
  for (const button of document.querySelectorAll("[data-submission-tab]")) {
    const active = button.getAttribute("data-submission-tab") === state.submissionDetailTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
    if (active) app.optional("submissionDetailPanel")?.setAttribute("aria-labelledby", button.id);
  }
  renderSubmissionDetailPanel();
}

function resultForDetail(detail) {
  return detail?.result || detail?.lastRunResult || null;
}

function submissionArtifactRunId() {
  return resultForDetail(state.selectedSubmission)?.runId || state.selectedSubmission?.runId || null;
}

function resultSummaryMarkup(detail) {
  const result = resultForDetail(detail) || {};
  const metrics = metricsFor({ ...detail, result });
  const cases = Array.isArray(result.cases) ? result.cases : [];
  const passed = cases.filter((item) => item.status === "ok").length;
  const storedCaseCount = Number(detail.resultSummary?.caseCount);
  const caseLabel = cases.length
    ? `${passed} / ${cases.length}`
    : Number.isFinite(storedCaseCount)
      ? `${storedCaseCount}개`
      : "확인 불가";
  const time = metricLabel(metrics, "maxTimeLabel", "maxTimeMs", "ms");
  const memory = metricLabel(metrics, "maxMemoryLabel", "maxMemoryBytes", "B");
  return `
    <div class="submission-summary-grid">
      <div><span>판정</span><strong>${app.escapeHtml(submissionStatusLabel(detail))}</strong></div>
      <div><span>테스트케이스</span><strong>${caseLabel}</strong></div>
      <div><span>최대 시간</span><strong>${app.escapeHtml(time)}</strong></div>
      <div><span>최대 메모리</span><strong>${app.escapeHtml(memory)}</strong></div>
    </div>
    ${detail.artifactAvailable === false ? '<p class="submission-notice">결과 요약은 보존됐지만 상세 테스트케이스 산출물은 정리되었습니다.</p>' : ""}
  `;
}

function sourceMarkup(detail) {
  if (typeof detail.sourceText !== "string") {
    return '<div class="submission-detail-empty"><strong>소스 파일을 찾을 수 없습니다.</strong><p>제출 결과 요약은 계속 확인할 수 있습니다.</p></div>';
  }
  const highlighted = app.highlightSourceCode(detail.sourceText, detail.languageId || detail.language);
  const notice = highlighted.skippedReason
    ? '<p class="submission-notice" role="status">큰 소스이므로 구문 강조를 생략했습니다.</p>'
    : "";
  return `${notice}<pre class="submission-source language-${highlighted.language}" tabindex="0" aria-label="제출 소스 코드 (${app.escapeHtml(highlighted.languageLabel)})"><code class="language-${highlighted.language}">${highlighted.html}</code></pre>`;
}

function diagnosticsMarkup(detail) {
  const result = resultForDetail(detail) || {};
  const details = result.failureDetails || detail.failureDetails || [];
  const messages = [
    result.compileLog,
    result.message,
    detail.error,
    ...details.map((item) => [item.label, item.target, item.message].filter(Boolean).join(" · ")),
  ].filter(Boolean);
  if (!messages.length) {
    return '<div class="submission-detail-empty"><strong>추가 진단이 없습니다.</strong><p>채점이 정상적으로 완료되었습니다.</p></div>';
  }
  return `<ul class="submission-diagnostics">${messages.map((message) => `<li>${app.escapeHtml(message)}</li>`).join("")}</ul>`;
}

function renderSubmissionDetailPanel() {
  const panel = app.optional("submissionDetailPanel");
  const detail = state.selectedSubmission;
  if (!panel || !detail) return;
  if (state.submissionDetailTab === "source") {
    panel.innerHTML = app.escapeHtml("") + sourceMarkup(detail);
    return;
  }
  if (state.submissionDetailTab === "diagnostics") {
    panel.innerHTML = app.escapeHtml("") + diagnosticsMarkup(detail);
    return;
  }
  if (state.submissionDetailTab === "cases") {
    const result = resultForDetail(detail);
    if (!result || !Array.isArray(result.cases) || !result.cases.length) {
    panel.innerHTML = '<div class="submission-detail-empty"><strong>표시할 테스트케이스 결과가 없습니다.</strong><p>상세 산출물이 정리됐거나 실행이 완료되지 않았습니다.</p></div>';
      return;
    }
    app.renderCaseResults(result, "submissionDetailPanel");
    if (detail.artifactAvailable === false) {
      panel.querySelectorAll("[data-case-artifact]").forEach((button) => button.remove());
      panel.insertAdjacentHTML(
        "afterbegin",
        '<p class="submission-notice">테스트케이스 판정은 보존됐지만 입력·출력·차이점 산출물은 정리되었습니다.</p>'
      );
    }
    return;
  }
  panel.innerHTML = app.escapeHtml("") + resultSummaryMarkup(detail);
}

function renderSubmissionDetail(detail, moveFocus) {
  state.selectedSubmission = detail;
  state.selectedSubmissionId = detail.submissionId;
  const badge = app.optional("submissionDetailBadge");
  if (badge) {
    badge.textContent = submissionStatusLabel(detail);
    badge.className = `badge ${submissionStatusClass(detail)}`;
  }
  const languageBadge = app.optional("submissionDetailLanguage");
  if (languageBadge) {
    const language = submissionLanguageMeta(detail);
    const languageTitle = language.raw && language.raw !== language.label
      ? `제출 언어: ${language.label} (${language.raw})`
      : `제출 언어: ${language.label}`;
    languageBadge.textContent = language.label;
    languageBadge.className = `submission-language language-${language.className}`;
    languageBadge.setAttribute("aria-label", languageTitle);
    languageBadge.title = languageTitle;
  }
  app.setText("submissionDetailTitle", `${detail.problemId || "문제 미상"} · ${detail.filename || "제출 코드"}`);
  app.setText(
    "submissionDetailMeta",
    `${submissionMeta(detail)} · ${formatSubmissionTime(detail.submittedAt || detail.createdAt)} · ${detail.runId || detail.jobId || detail.submissionId}`
  );
  const deleteButton = app.optional("submissionDeleteButton");
  const deleteHint = app.optional("submissionDeleteHint");
  const active = ["queued", "running"].includes(detail.lifecycle);
  if (deleteButton) {
    deleteButton.disabled = Boolean(detail.legacy) || active;
    deleteButton.title = detail.legacy
      ? "이전 캐시 코드 기록은 기존 캐시 화면에서 정리할 수 있습니다."
      : active
        ? "대기 중이거나 실행 중인 제출은 삭제할 수 없습니다."
        : "제출 기록과 보존된 소스를 삭제합니다.";
  }
  if (deleteHint) {
    const message = detail.legacy
      ? "이전 캐시 코드 기록은 기존 캐시 화면에서 정리할 수 있습니다."
      : active
        ? "이 제출은 현재 대기 또는 실행 중이므로 완료되거나 취소된 뒤 삭제할 수 있습니다."
        : "";
    deleteHint.textContent = message;
    deleteHint.classList.toggle("hidden", !message);
  }
  app.optional("submissionDetailEmpty")?.classList.add("hidden");
  app.optional("submissionDetailContent")?.classList.remove("hidden");
  app.optional("submissionsDrawer")?.classList.add("has-detail");
  setSubmissionTab(state.submissionDetailTab);
  renderSubmissions({
    submissions: state.submissions,
    page: state.submissionsPage,
    total: Number(app.optional("submissionsCount")?.textContent.match(/\d+/)?.[0]) || state.submissions.length,
    totalPages: state.submissionsTotalPages,
  });
  if (moveFocus) window.setTimeout(() => app.optional("submissionDetailTitle")?.focus(), 0);
}

async function selectSubmission(submissionId, { moveFocus = true } = {}) {
  if (!submissionId) return;
  state.selectedSubmissionId = submissionId;
  const token = ++state.submissionDetailToken;
  const panel = app.optional("submissionDetailPanel");
  if (panel) panel.innerHTML = '<div class="submission-detail-empty">제출 상세를 불러오는 중입니다.</div>';
  try {
    const detail = await app.api(`/api/submissions/${encodeURIComponent(submissionId)}`);
    if (token !== state.submissionDetailToken) return;
    renderSubmissionDetail(detail, moveFocus);
  } catch (error) {
    if (token !== state.submissionDetailToken || !panel) return;
    app.optional("submissionDetailEmpty")?.classList.add("hidden");
    app.optional("submissionDetailContent")?.classList.remove("hidden");
    panel.innerHTML = `<div class="submission-detail-empty"><strong>제출 상세를 불러오지 못했습니다.</strong><span>${app.escapeHtml(error.message)}</span><button type="button" data-submission-detail-retry="${app.escapeHtml(submissionId)}">다시 시도</button></div>`;
  }
}

async function openSubmissions(submissionId = null) {
  app.openModal("submissionsDrawer");
  if (submissionId) state.selectedSubmissionId = submissionId;
  await refreshSubmissions();
  if (submissionId) await selectSubmission(submissionId);
}

function setSubmissionsScope(scope) {
  state.submissionsScope = scope === "all" ? "all" : "problem";
  state.submissionsPage = 1;
  clearSubmissionDetail();
  void app.withErrors(refreshSubmissions);
}

function resetSubmissionFilters() {
  for (const id of [
    "submissionsQueryInput",
    "submissionsStatusFilter",
    "submissionsLanguageFilter",
    "submissionsProfileFilter",
  ]) {
    const input = app.optional(id);
    if (input) input.value = "";
  }
  const order = app.optional("submissionsOrderSelect");
  if (order) order.value = "newest";
  state.submissionsPage = 1;
  void app.withErrors(refreshSubmissions);
}

async function loadSelectedSubmission() {
  const detail = state.selectedSubmission;
  if (!detail || typeof detail.sourceText !== "string") return;
  const currentText = app.optional("sourceTextInput")?.value || "";
  const currentFilename = app.optional("filenameInput")?.value || "";
  const dirty = Boolean(currentText || currentFilename)
    && (currentText !== detail.sourceText || currentFilename !== detail.filename);
  if (dirty && !window.confirm("편집 중인 코드가 있습니다. 선택한 제출 코드로 바꿀까요?")) return;
  app.saveProblemDraft?.(state.selectedProblem);
  if (detail.problemId && state.problems.some((problem) => problem.problemId === detail.problemId)) {
    state.selectedProblem = detail.problemId;
    app.$("problemSelect").value = detail.problemId;
    app.renderProblemSelection();
    await app.loadSamples();
  }
  app.setMode("text");
  app.$("filenameInput").value = detail.filename || "";
  app.$("sourceTextInput").value = detail.sourceText;
  const language = detail.languageId || detail.language || "";
  if ([...app.$("languageHint").options].some((option) => option.value === language)) {
    app.$("languageHint").value = language;
  }
  app.updateLanguageBadge();
  app.updateEditorView();
  app.syncEditorScroll();
  app.closeModals();
  app.showToast(`제출 코드를 불러왔습니다: ${detail.filename || detail.submissionId}`);
}

async function deleteSelectedSubmission() {
  const detail = state.selectedSubmission;
  if (!detail) return;
  if (["queued", "running"].includes(detail.lifecycle)) {
    app.showToast("대기 중이거나 실행 중인 제출은 삭제할 수 없습니다.", "error");
    return;
  }
  if (!window.confirm(`${detail.filename || "제출"} 기록과 보존된 소스를 삭제할까요?`)) return;
  await app.api(`/api/submissions/${encodeURIComponent(detail.submissionId)}`, { method: "DELETE" });
  app.showToast("제출 기록을 삭제했습니다.");
  clearSubmissionDetail();
  await Promise.all([refreshSubmissions(), refreshRecentSubmissions()]);
}

async function clearAllSubmissions() {
  if (state.hasActiveSubmissions) {
    app.showToast("대기 중이거나 실행 중인 제출이 있어 전체 삭제할 수 없습니다.", "error");
    return;
  }
  const confirmation = window.prompt(
    '모든 제출 기록과 보존된 소스를 삭제합니다. 이 작업은 되돌릴 수 없습니다. 계속하려면 "전체 삭제"를 입력하세요.'
  );
  if (confirmation !== "전체 삭제") return;
  await app.api("/api/submissions?confirm=true", { method: "DELETE" });
  clearSubmissionDetail();
  await Promise.all([refreshSubmissions(), refreshRecentSubmissions()]);
  app.optional("submissionsResetButton")?.focus();
  app.showToast("모든 제출 기록을 삭제했습니다. 이전 캐시 코드 기록은 유지됩니다.");
}

function showSubmissionListOnMobile() {
  app.optional("submissionsDrawer")?.classList.remove("has-detail");
  const selected = app.optional("submissionsList")?.querySelector(`[data-submission-id="${CSS.escape(state.selectedSubmissionId || "")}"]`);
  if (selected instanceof HTMLElement) selected.focus();
}

function onSubmissionsClosed() {
  state.submissionDetailToken += 1;
  if (submissionPollTimer) window.clearTimeout(submissionPollTimer);
  submissionPollTimer = null;
}

function bindSubmissions() {
  app.on("submissionsButton", "click", () => void app.withErrors(() => openSubmissions()));
  app.on("recentSubmissionsAllButton", "click", () => void app.withErrors(() => openSubmissions()));
  app.on("submissionsProblemScopeButton", "click", () => setSubmissionsScope("problem"));
  app.on("submissionsAllScopeButton", "click", () => setSubmissionsScope("all"));
  app.on("submissionsResetButton", "click", resetSubmissionFilters);
  app.on("submissionsClearAllButton", "click", () => void app.withErrors(clearAllSubmissions));
  app.on("submissionsPrevButton", "click", () => {
    state.submissionsPage = Math.max(1, state.submissionsPage - 1);
    void app.withErrors(refreshSubmissions);
  });
  app.on("submissionsNextButton", "click", () => {
    state.submissionsPage = Math.min(state.submissionsTotalPages, state.submissionsPage + 1);
    void app.withErrors(refreshSubmissions);
  });
  for (const id of ["submissionsStatusFilter", "submissionsLanguageFilter", "submissionsProfileFilter", "submissionsOrderSelect"]) {
    app.on(id, "change", () => {
      state.submissionsPage = 1;
      void app.withErrors(refreshSubmissions);
    });
  }
  app.on("submissionsQueryInput", "input", () => {
    if (queryTimer) window.clearTimeout(queryTimer);
    queryTimer = window.setTimeout(() => {
      state.submissionsPage = 1;
      void app.withErrors(refreshSubmissions);
    }, 250);
  });
  app.on("submissionLoadButton", "click", () => void app.withErrors(loadSelectedSubmission));
  app.on("submissionDeleteButton", "click", () => void app.withErrors(deleteSelectedSubmission));
  app.on("submissionBackButton", "click", showSubmissionListOnMobile);
  for (const tab of document.querySelectorAll("[data-submission-tab]")) {
    tab.addEventListener("click", () => setSubmissionTab(tab.getAttribute("data-submission-tab")));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      const tabs = [...document.querySelectorAll("[data-submission-tab]")];
      const offset = event.key === "ArrowRight" ? 1 : -1;
      const next = tabs[(tabs.indexOf(tab) + offset + tabs.length) % tabs.length];
      event.preventDefault();
      next.focus();
      setSubmissionTab(next.getAttribute("data-submission-tab"));
    });
  }
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const item = target.closest("[data-submission-id]");
    if (item) {
      const id = item.getAttribute("data-submission-id");
      if (item.closest("#recentSubmissionsList")) {
        void app.withErrors(() => openSubmissions(id));
      } else {
        void app.withErrors(() => selectSubmission(id));
      }
      return;
    }
    if (target.closest("[data-submissions-reset]")) resetSubmissionFilters();
    if (target.closest('[data-submissions-retry="recent"]')) void refreshRecentSubmissions();
    if (target.closest('[data-submissions-retry="list"]')) void refreshSubmissions();
    const retryId = target.closest("[data-submission-detail-retry]")?.getAttribute("data-submission-detail-retry");
    if (retryId) void selectSubmission(retryId);
  });
}

Object.assign(app, {
  bindSubmissions,
  onSubmissionsClosed,
  openSubmissions,
  refreshRecentSubmissions,
  refreshSubmissions,
  submissionArtifactRunId,
});
