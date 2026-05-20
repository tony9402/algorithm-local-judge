import { api, normalizeErrorDetail } from "./app/api.js";
import { $, optional, resetWorkspaceScroll, setText } from "./app/dom.js";
import { parseSseBlock, streamProgressDetail } from "./app/sse.js";
import {
  DELETE_CONFIRM_PHRASE,
  EDITOR_HISTORY_LIMIT,
  EDITOR_INDENT,
  EDITOR_SETTINGS_KEY,
  EXPECTED_STATUS_BY_TOKEN,
  EXTENSIONS,
  FILE_ROLES,
  LANGUAGE_BY_EXTENSION,
  LAST_RESULTS_KEY,
  METADATA_TIMEOUT_FIELDS,
  METADATA_TOOL_FIELDS,
  PACK_JOB_KEY,
  PACK_OUTPUT_DIR,
  PERSISTED_VIEW_KEY,
  PROBLEM_TASK_LOCK_NAME,
  RUN_ALL_LOCK_KEY,
  RUN_ALL_LOCK_TTL_MS,
  SAFE_PROBLEM_ID,
  SAFE_SOLUTION_NAME,
  SAVE_BEFORE_ACTIONS,
  STATUS_LABELS,
  TAB_CONFIGS,
  TAB_INSTANCE_ID,
  runAllChannel,
  state,
} from "./app/state.js";
import { readStorage, removeStorage, writeStorage } from "./app/storage.js";

const ACTIONS = {
  saveMetadata: () => saveMetadata(),
  openDeleteProblem: () => openDeleteProblemModal(),
  compileCases: () => compileCases(),
  compileGenerator: () => compileTool("generator", "Generator"),
  generateSample: () => generateData("sample"),
  generateHidden: () => generateData("hidden"),
  compileValidator: () => compileTool("validator", "Validator"),
  validateSample: () => validateAllData(),
  compileChecker: () => compileTool("checker", "Checker"),
  compileReference: () => compileTool("solution", "Reference solution"),
  compileTools: () => compileTools(),
  newSolution: () => openSolutionCreateModal(),
  uploadSolutions: () => openSolutionUpload(),
  verifySolutions: () => verifySolutions(),
  runAllChecks: () => runAllChecksOnce(),
  buildPack: () => buildPack(),
  buildAllPacks: () => buildAllPacksOnce(),
};

if ("scrollRestoration" in window.history) {
  window.history.scrollRestoration = "manual";
}

function storedLastResults() {
  const results = readStorage(LAST_RESULTS_KEY);
  return results && typeof results === "object" ? results : {};
}

function persistProblemLastResult(patch, problemId = state.selectedProblem) {
  if (!problemId) return;
  const results = storedLastResults();
  results[problemId] = {
    ...(results[problemId] || {}),
    ...patch,
    problemId,
    updatedAt: Date.now(),
  };
  writeStorage(LAST_RESULTS_KEY, results);
}

function currentProblemResult(problemId = state.selectedProblem) {
  return problemId ? storedLastResults()[problemId] || null : null;
}

function hasFreshFullTest(problemId = state.selectedProblem) {
  const result = currentProblemResult(problemId);
  return Boolean(result?.fullTest?.passed && !result?.dirtyAfterFullTest);
}

function markFullTestDirty(reason = "변경사항이 저장되어 전체 테스트가 필요합니다.") {
  if (!state.selectedProblem) return;
  const current = currentProblemResult() || {};
  persistProblemLastResult({
    ...current,
    dirtyAfterFullTest: true,
    dirtyReason: reason,
    lastPackResult: null,
  });
  state.lastFullTest = current.fullTest || null;
  state.lastPackResult = null;
  updateBuildPanel();
  renderTabFiles();
}

function clearProblemLastResult(problemId = state.selectedProblem) {
  if (!problemId) return;
  const results = storedLastResults();
  if (!results[problemId]) return;
  delete results[problemId];
  writeStorage(LAST_RESULTS_KEY, results);
}

function updateMobileHeader(title = null, meta = null) {
  const problemTitle = title || optional("problemTitle")?.textContent || "문제를 선택하세요";
  const problemMeta = meta || (state.selectedProblem ? "문제 목록" : "문제 목록 열기");
  setText("mobileHeaderTitle", problemTitle);
  setText("mobileHeaderMeta", problemMeta);
  const menuAction = document.body.classList.contains("sidebar-open")
    ? "문제 목록 닫기"
    : "문제 목록 열기";
  optional("sidebarToggle")?.setAttribute("aria-label", `${menuAction}: ${problemTitle}`);
}

function nextViewSeq() {
  state.viewSeq += 1;
  return state.viewSeq;
}

function isCurrentView(seq) {
  return seq === state.viewSeq;
}

function setControlsDisabled(disabled) {
  document.body.setAttribute("aria-busy", disabled ? "true" : "false");
  for (const element of document.querySelectorAll("button, input, select, textarea")) {
    element.disabled = disabled;
  }
  updateGlobalActionState();
  updateDeleteProblemButton();
}

function setSidebarOpen(open) {
  document.body.classList.toggle("sidebar-open", open);
  optional("sidebarToggle")?.setAttribute("aria-expanded", open ? "true" : "false");
  updateMobileHeader();
}

function toggleSidebar() {
  setSidebarOpen(!document.body.classList.contains("sidebar-open"));
}

function closeSidebar() {
  setSidebarOpen(false);
}

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

function renderProgressPanel() {
  const panel = optional("progressPanel");
  if (!panel) return;
  panel.classList.toggle("hidden", !state.progress.active);
  if (!state.progress.active) return;

  const steps = state.progress.steps;
  const total = Math.max(steps.length, 1);
  const done = progressDoneCount();
  const percent = Math.round((done / total) * 100);
  const fill = optional("progressBarFill");
  if (fill) fill.style.width = `${percent}%`;

  const running = steps.find((step) => step.status === "running");
  const failed = steps.find((step) => step.status === "error");
  const summary = failed
    ? `${failed.label} 단계에서 확인이 필요합니다.`
    : running
      ? `${running.label} 진행 중 · ${done}/${steps.length}단계 완료`
      : `${done}/${steps.length}단계 완료`;
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

function beginProgress(title, steps = []) {
  state.progress = {
    active: true,
    title,
    steps: steps.map((step) => ({ ...step })),
    insightTitle: "현재 작업",
    insightBody: "전체 테스트를 준비하고 있습니다.",
  };
  setText("loadingTitle", title);
  setText("loadingMessage", "단계별 진행 상황을 확인하고 있습니다.");
  renderProgressPanel();
}

function completeProgress() {
  state.progress.active = false;
  renderProgressPanel();
}

function setProgressInsight(title, body) {
  state.progress.insightTitle = title || "현재 작업";
  state.progress.insightBody = body || "단계가 완료되면 결과 요약이 갱신됩니다.";
  renderProgressPanel();
}

function setProgressStep(index, status, detail = "") {
  if (!state.progress.steps[index]) return;
  state.progress.steps[index].status = status;
  state.progress.steps[index].detail = detail;
  const running = state.progress.steps.find((step) => step.status === "running");
  const done = progressDoneCount();
  setText("loadingTitle", state.progress.title || "진행 중");
  setText("loadingMessage", running ? running.label : `${done}/${state.progress.steps.length} 완료`);
  renderProgressPanel();
}

function updateRunningProgressDetail(detail) {
  const runningIndex = state.progress.steps.findIndex((step) => step.status === "running");
  if (runningIndex < 0) return;
  state.progress.steps[runningIndex].detail = detail;
  renderProgressPanel();
}

function hideLastRunPanel() {
  optional("lastRunPanel")?.classList.add("hidden");
}

function shouldDisplayLastRunPanel(tabId = state.selectedTab) {
  return tabId !== "build" && tabId !== "solutions";
}

function renderLastRunPanel() {
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

function showLastRun(title, summary, type = "success", options = {}) {
  state.lastRun = { title, summary, type, updatedAt: Date.now() };
  if (options.persist !== false) {
    persistProblemLastResult({ lastRun: state.lastRun }, options.problemId);
  }
  renderLastRunPanel();
}

function errorKindForDetail(detail) {
  const normalized = normalizeErrorDetail(detail);
  const text = normalized.toLowerCase();
  const includesAny = (...tokens) => tokens.some((token) => text.includes(token));
  if (includesAny("timed out", "timeout")) {
    return {
      label: "시간 초과",
      hint: "제한 시간, 무한 루프, 입력 크기와 생성/검증 로직의 복잡도를 확인하세요.",
    };
  }
  if (includesAny("required tool not found", "install one of")) {
    return {
      label: "환경 설정 오류",
      hint: "로컬에 필요한 컴파일러나 런타임이 설치되어 있고 PATH 또는 환경 변수가 맞는지 확인하세요.",
    };
  }
  if (includesAny("cases.yml compile failed", "cases.yml: invalid", "unknown variable")) {
    return {
      label: "cases.yml 설정 오류",
      hint: "cases.yml의 profile, repeat/matrix, 변수명, 들여쓰기와 line 정보를 먼저 확인하세요.",
    };
  }
  if (includesAny("compile error", "compile failed", "java compile failed", "compiler output")) {
    return {
      label: "컴파일 오류",
      hint: "대상 소스의 문법, include/import, 타입, 컴파일 로그 경로와 compiler output을 확인하세요.",
    };
  }
  if (includesAny("validator failed", "expected eof", "expected eoln", "not in range", "violates")) {
    return {
      label: "데이터 검증 실패",
      hint: "generator가 만든 입력과 validator가 읽는 값의 개수, 줄바꿈, 제약 조건이 맞는지 확인하세요.",
    };
  }
  if (includesAny("checker self-check failed")) {
    return {
      label: "체커 검증 실패",
      hint: "checker가 정답 출력과 동일한 출력도 허용하는지, checker 인자 처리와 stderr를 확인하세요.",
    };
  }
  if (includesAny("solution expectation check failed")) {
    return {
      label: "솔루션 기대 결과 불일치",
      hint: "기대 결과가 파일명과 맞는지, 실제 판정과 메시지를 솔루션 탭의 실패 항목에서 확인하세요.",
    };
  }
  if (includesAny("solution failed")) {
    return {
      label: "기준 정답 런타임 오류",
      hint: "기준 정답이 생성된 입력에서 예외 종료했는지, stderr와 입력 preview를 확인하세요.",
    };
  }
  if (includesAny("generator failed for case", "generator runtime error", "exit code")) {
    return {
      label: "Generator 런타임 오류",
      hint: "실패한 case의 seed/args와 generator.cpp의 예외 종료, stderr를 확인하세요.",
    };
  }
  if (includesAny("generator script failed", "generator script produced no cases")) {
    return {
      label: "데이터 생성 오류",
      hint: "cases.yml에서 선택된 profile과 generator 출력 파일 생성 여부를 확인하세요.",
    };
  }
  if (includesAny("pack build")) {
    return {
      label: "팩 빌드 오류",
      hint: "전체 테스트 통과 상태, 출력 폴더, pack 설정과 백그라운드 작업 로그를 확인하세요.",
    };
  }
  return {
    label: "실행 오류",
    hint: "실패 단계와 원문 상세를 기준으로 관련 파일을 확인하세요.",
  };
}

function formatOperationFailure(detail, rows = []) {
  const normalized = normalizeErrorDetail(detail) || "알 수 없는 문제가 발생했습니다.";
  const kind = errorKindForDetail(normalized);
  return [
    `오류 유형: ${kind.label}`,
    kind.hint ? `확인 포인트: ${kind.hint}` : "",
    ...rows.filter(Boolean),
    "에러 상세",
    normalized,
  ].filter(Boolean).join("\n");
}

function restoreProblemLastResult(problemId = state.selectedProblem) {
  const result = storedLastResults()[problemId];
  state.lastSolutionVerification = result?.solutionVerification || null;
  state.lastFullTest = result?.fullTest || null;
  state.lastPackResult = result?.lastPackResult || null;
  state.lastRun = result?.lastRun || null;
  state.dirtySolutionPaths = Array.isArray(result?.dirtySolutionPaths)
    ? result.dirtySolutionPaths.map(normalizedSolutionPath)
    : [];
  renderLastRunPanel();
  updateBuildPanel();
}

function statusLabelForResult(status) {
  return STATUS_LABELS[status] || status || "-";
}

function statusToneForResult(status) {
  if (status === "ok" || status === "accepted") return "ok";
  if (status === "time_limit" || status === "memory_limit") return "warn";
  return "bad";
}

function formatDurationMs(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  if (numeric >= 1000) return `${(numeric / 1000).toFixed(2)} s`;
  return `${Math.round(numeric)} ms`;
}

function formatMemoryBytes(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  if (numeric >= 1024 * 1024) return `${(numeric / 1024 / 1024).toFixed(1)} MB`;
  if (numeric >= 1024) return `${(numeric / 1024).toFixed(1)} KB`;
  return `${Math.round(numeric)} B`;
}

function solutionCheckCases(check) {
  return Array.isArray(check?.cases) ? check.cases : [];
}

function solutionCaseName(item) {
  return item?.case || item?.caseId || item?.name || "-";
}

function solutionCaseStatus(item) {
  return item?.status || "unknown";
}

function solutionCaseTime(item) {
  return item?.timeMs ?? item?.elapsedMs ?? item?.time ?? null;
}

function solutionCaseMemory(item) {
  return item?.memoryBytes ?? item?.memory ?? item?.memoryKb ?? null;
}

function maxMetricFromCases(cases, getter) {
  const values = cases
    .map(getter)
    .map((value) => (value === null || value === undefined ? NaN : Number(value)))
    .filter(Number.isFinite);
  return values.length ? Math.max(...values) : null;
}

function solutionCheckMetrics(check) {
  const cases = solutionCheckCases(check);
  const metrics = check?.metrics || {};
  const maxTimeMs = metrics.maxTimeMs ?? maxMetricFromCases(cases, solutionCaseTime);
  const maxMemoryBytes = metrics.maxMemoryBytes ?? maxMetricFromCases(cases, solutionCaseMemory);
  const okCases = cases.filter((item) => solutionCaseStatus(item) === "ok").length;
  return {
    totalCases: cases.length,
    okCases,
    maxTimeMs,
    maxMemoryBytes,
  };
}

function renderSolutionCaseRows(check) {
  const cases = solutionCheckCases(check);
  if (!cases.length) return "";
  const rows = cases
    .map((item) => {
      const status = solutionCaseStatus(item);
      return `
        <div class="solution-case-row ${statusToneForResult(status)}">
          <span class="solution-case-name" title="${escapeHtml(solutionCaseName(item))}">
            ${escapeHtml(solutionCaseName(item))}
          </span>
          <strong>${escapeHtml(status === "ok" ? "OK" : statusLabelForResult(status))}</strong>
          <span>${escapeHtml(formatDurationMs(solutionCaseTime(item)))}</span>
          <span>${escapeHtml(formatMemoryBytes(solutionCaseMemory(item)))}</span>
        </div>
      `;
    })
    .join("");
  return `
    <div class="solution-case-table" aria-label="테스트 케이스별 채점 결과">
      <div class="solution-case-row head">
        <span>케이스</span>
        <span>결과</span>
        <span>시간</span>
        <span>메모리</span>
      </div>
      ${rows}
    </div>
  `;
}

function renderSolutionCasesBody(check) {
  const metrics = solutionCheckMetrics(check);
  const message = normalizeErrorDetail(check?.message);
  return `
    <div class="solution-cases-summary">
      <span><small>기대</small><strong>${escapeHtml(statusLabelForResult(check.expectedStatus))}</strong></span>
      <span><small>실제</small><strong>${escapeHtml(statusLabelForResult(check.actualStatus))}</strong></span>
      <span><small>케이스</small><strong>${metrics.totalCases ? `${metrics.okCases}/${metrics.totalCases}` : "-"}</strong></span>
      <span><small>최대 시간</small><strong>${escapeHtml(formatDurationMs(metrics.maxTimeMs))}</strong></span>
      <span><small>최대 메모리</small><strong>${escapeHtml(formatMemoryBytes(metrics.maxMemoryBytes))}</strong></span>
      <span><small>run</small><strong>${escapeHtml(check.runId || "-")}</strong></span>
    </div>
    ${message ? `<div class="solution-cases-message">${escapeHtml(message)}</div>` : ""}
    ${
      metrics.totalCases
        ? renderSolutionCaseRows(check)
        : `<div class="empty-state">아직 표시할 테스트 케이스 결과가 없습니다. 개별 테스트나 기대 결과 검증을 먼저 실행하세요.</div>`
    }
  `;
}

function solutionCheckSource(check) {
  return check.source || check.path || check.file || "알 수 없는 솔루션";
}

function failedSolutionChecks(result) {
  return (result?.checks || []).filter((check) => !check.passed);
}

function normalizedSolutionPath(value) {
  return String(value || "").replace(/^\.?\//, "");
}

function dirtySolutionSet() {
  return new Set((state.dirtySolutionPaths || []).map(normalizedSolutionPath));
}

function setDirtySolutionPaths(paths) {
  state.dirtySolutionPaths = Array.from(
    new Set((paths || []).map(normalizedSolutionPath).filter(Boolean))
  );
  persistProblemLastResult({ dirtySolutionPaths: state.dirtySolutionPaths });
}

function removeSolutionChecks(paths) {
  if (!state.lastSolutionVerification?.checks?.length) return;
  const removed = new Set((paths || []).map(normalizedSolutionPath));
  if (!removed.size) return;
  state.lastSolutionVerification = {
    ...state.lastSolutionVerification,
    checks: state.lastSolutionVerification.checks.filter(
      (check) => !removed.has(normalizedSolutionPath(solutionCheckSource(check)))
    ),
  };
  persistProblemLastResult({ solutionVerification: state.lastSolutionVerification });
}

function markSolutionDirty(path, reason = "솔루션 변경으로 재검증이 필요합니다.", options = {}) {
  const dirty = dirtySolutionSet();
  if (options.oldPath) {
    dirty.delete(normalizedSolutionPath(options.oldPath));
    removeSolutionChecks([options.oldPath]);
  }
  dirty.add(normalizedSolutionPath(path));
  setDirtySolutionPaths(Array.from(dirty));
  markFullTestDirty(reason);
  renderSolutionValidationSummary();
  renderTabFiles();
}

function markAllSolutionsDirty(reason = "데이터 또는 기준 도구 변경으로 모든 솔루션 재검증이 필요합니다.") {
  setDirtySolutionPaths(solutionFilePaths());
  markFullTestDirty(reason);
  renderSolutionValidationSummary();
  renderTabFiles();
}

function clearSolutionDirty(paths) {
  const completed = new Set((paths || []).map(normalizedSolutionPath));
  if (!completed.size) return;
  setDirtySolutionPaths(state.dirtySolutionPaths.filter((path) => !completed.has(path)));
}

function solutionCheckForPath(path) {
  const checks = state.lastSolutionVerification?.checks || [];
  const normalizedPath = normalizedSolutionPath(path);
  return checks.find((check) => {
    const source = normalizedSolutionPath(solutionCheckSource(check));
    return source === normalizedPath || source.endsWith(`/${normalizedPath}`);
  });
}

function solutionValidationStatusForFile(path) {
  if (dirtySolutionSet().has(normalizedSolutionPath(path))) {
    return {
      className: "stale",
      label: "변경 후 재검증 필요",
      title: `${path} · 소스 변경 후 솔루션 테스트 필요`,
    };
  }
  if (!state.lastSolutionVerification) return null;
  const check = solutionCheckForPath(path);
  if (!check) return null;
  const expected = statusLabelForResult(check.expectedStatus);
  const actual = statusLabelForResult(check.actualStatus);
  if (check.passed) {
    return {
      className: "match",
      label: `기대 ${expected} · 일치`,
      title: `${path} · 기대 ${expected} · 일치`,
    };
  }
  const details = `기대 ${expected} · 실제 ${actual}`;
  return {
    className: "mismatch",
    label: details,
    title: `${path} · ${details}`,
  };
}

function fullTestStatusForFile(path) {
  const result = currentProblemResult();
  if (!result?.fullTest && !result?.dirtyAfterFullTest) return null;
  const role = roleForFile(path);
  if (result?.dirtyAfterFullTest) {
    return {
      className: "stale",
      label: "변경 후 재검증 필요",
      title: `${path} · ${role} · 변경 후 전체 테스트 필요`,
    };
  }
  if (result.fullTest?.passed) {
    return {
      className: "match",
      label: "전체 테스트 통과",
      title: `${path} · ${role} · 전체 테스트 통과`,
    };
  }
  return {
    className: "mismatch",
    label: "최근 전체 테스트 실패",
    title: `${path} · ${role} · 최근 전체 테스트 실패`,
  };
}

function validationStatusForFile(path) {
  return solutionValidationStatusForFile(path) || fullTestStatusForFile(path);
}

function solutionCheckDetailRows(check, options = {}) {
  const metrics = solutionCheckMetrics(check);
  const rows = [
    ["기대", statusLabelForResult(check.expectedStatus)],
    ["실제", statusLabelForResult(check.actualStatus)],
    ["케이스", metrics.totalCases ? `${metrics.okCases}/${metrics.totalCases}` : "-"],
    ["최대 시간", formatDurationMs(metrics.maxTimeMs)],
    ["최대 메모리", formatMemoryBytes(metrics.maxMemoryBytes)],
    ["실행", check.runId || "-"],
    ["메시지", normalizeErrorDetail(check.message) || "-"],
  ];
  if (options.includeFile) rows.unshift(["파일", solutionCheckSource(check)]);
  return rows
    .map(
      ([label, value]) => `
        <div class="solution-validation-detail-row ${label === "메시지" ? "message" : ""}">
          <span>${escapeHtml(label)}</span>
          <strong title="${escapeHtml(value)}">${escapeHtml(value)}</strong>
        </div>
      `
    )
    .join("");
}

function renderSolutionFailureItem(check) {
  const source = solutionCheckSource(check);
  return `
    <li class="solution-validation-failure">
      <span class="solution-validation-source" title="${escapeHtml(source)}">${escapeHtml(source)}</span>
      ${solutionCheckDetailRows(check)}
    </li>
  `;
}

function formatSolutionFailureSummary(result, options = {}) {
  const failed = failedSolutionChecks(result);
  if (!failed.length) return "솔루션 기대 결과와 다른 항목이 있습니다.";
  const limit = options.limit ?? 8;
  const shown = failed.slice(0, limit);
  const lines = [
    `${result.profile || "hidden"} profile에서 기대 결과와 다른 솔루션 ${failed.length}개`,
  ];
  for (const check of shown) {
    lines.push(
      `- ${solutionCheckSource(check)}`,
      `  기대: ${statusLabelForResult(check.expectedStatus)} · 실제: ${statusLabelForResult(check.actualStatus)}`
    );
    if (check.runId) lines.push(`  run: ${check.runId}`);
    if (check.message) {
      const message = normalizeErrorDetail(check.message);
      if (message) lines.push(`  ${message}`);
    }
  }
  if (failed.length > shown.length) {
    lines.push(`- 외 ${failed.length - shown.length}개 솔루션은 솔루션 탭에서 확인하세요.`);
  }
  return lines.join("\n");
}

function solutionFilePaths() {
  return filesForTab("solutions").map((file) => normalizedSolutionPath(file.path));
}

function mergeSolutionVerification(previous, partial) {
  const currentPaths = solutionFilePaths();
  const currentPathSet = new Set(currentPaths);
  const byPath = new Map();
  for (const check of previous?.checks || []) {
    const path = normalizedSolutionPath(solutionCheckSource(check));
    if (currentPathSet.has(path)) byPath.set(path, check);
  }
  for (const check of partial?.checks || []) {
    byPath.set(normalizedSolutionPath(solutionCheckSource(check)), check);
  }
  const checks = currentPaths
    .map((path) => byPath.get(path))
    .filter(Boolean);
  const everyCurrentPathChecked = currentPaths.every((path) => byPath.has(path));
  const verifiedNow = partial?.checks?.length || 0;
  const maintainedCount = Math.max(0, checks.length - verifiedNow);
  return {
    ...(previous || {}),
    ...partial,
    checks,
    passed: checks.every((check) => check.passed),
    complete: everyCurrentPathChecked,
    verifiedCount: verifiedNow,
    totalCount: currentPaths.length,
    skippedCount: 0,
    maintainedCount,
    incremental: verifiedNow < currentPaths.length,
  };
}

function pathsNeedingSolutionVerification(options = {}) {
  const allPaths = solutionFilePaths();
  if (options.paths?.length) return options.paths.map(normalizedSolutionPath);
  if (options.forceAll || !state.lastSolutionVerification) return allPaths;
  const checked = new Set(
    (state.lastSolutionVerification.checks || []).map((check) =>
      normalizedSolutionPath(solutionCheckSource(check))
    )
  );
  const dirty = dirtySolutionSet();
  return allPaths.filter((path) => dirty.has(path) || !checked.has(path));
}

function clearSolutionVerification() {
  state.lastSolutionVerification = null;
  state.lastFullTest = null;
  state.lastPackResult = null;
  state.lastRun = null;
  state.dirtySolutionPaths = [];
  clearProblemLastResult();
  hideLastRunPanel();
  updateBuildPanel();
  renderSolutionValidationSummary();
  renderTabFiles();
}

function discardPersistedSolutionResult() {
  state.lastSolutionVerification = null;
  state.lastFullTest = null;
  state.lastPackResult = null;
  state.lastRun = null;
  state.dirtySolutionPaths = [];
  clearProblemLastResult();
  hideLastRunPanel();
  updateBuildPanel();
}

function showLoading(message = "작업을 처리하는 중입니다.") {
  state.loadingDepth += 1;
  setText("loadingTitle", "로딩 중");
  setText("loadingMessage", message);
  if (!state.progress.active) renderProgressPanel();
  $("loadingOverlay").classList.remove("hidden");
  setControlsDisabled(true);
}

function hideLoading() {
  state.loadingDepth = Math.max(0, state.loadingDepth - 1);
  if (state.loadingDepth > 0) return;
  $("loadingOverlay").classList.add("hidden");
  completeProgress();
  setControlsDisabled(false);
  updateSolutionPreview();
  updateSolutionRenamePreview();
}

function forceHideLoading() {
  state.loadingDepth = 0;
  $("loadingOverlay").classList.add("hidden");
  completeProgress();
  setControlsDisabled(false);
}

async function withLoading(message, action) {
  showLoading(message);
  try {
    return await action();
  } finally {
    hideLoading();
  }
}

async function withErrors(action, message = "작업을 처리하는 중입니다.") {
  try {
    return await withLoading(message, action);
  } catch (error) {
    forceHideLoading();
    const title = message.replace(/ 작업을 실행하는 중입니다\.?$/, " 실패").replace(/하는 중입니다\.?$/, " 실패");
    showAlert(error.message, "error", { title: title || "작업 실패", timeout: 9000 });
    return null;
  }
}

async function withInlineErrors(action) {
  try {
    return await action();
  } catch (error) {
    forceHideLoading();
    showAlert(error.message, "error", { title: "작업 실패", timeout: 9000 });
    return null;
  }
}

function currentRunAllLock() {
  const lock = readStorage(RUN_ALL_LOCK_KEY);
  if (!lock?.token || !lock?.expiresAt) return null;
  if (Number(lock.expiresAt) <= Date.now()) {
    removeStorage(RUN_ALL_LOCK_KEY);
    return null;
  }
  return lock;
}

function announceRunAllLock() {
  runAllChannel?.postMessage({ type: "run-all-lock-changed" });
}

function updateRunAllButton() {
  const button = optional("runAllButton");
  if (!button) return;
  const lock = currentRunAllLock();
  const lockedByAnotherTab = Boolean(lock && lock.owner !== TAB_INSTANCE_ID);
  const packActive = Boolean(state.activePackJob);
  button.disabled = lockedByAnotherTab || packActive || document.body.getAttribute("aria-busy") === "true";
  button.textContent = packActive
    ? "팩 빌드 진행 중"
    : lockedByAnotherTab
      ? "전체 테스트 진행 중"
      : "전체 테스트";
  button.title = packActive
    ? packJobSummary(state.activePackJob)
    : lockedByAnotherTab
    ? `${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)} 시작`
    : "";
}

function updatePackButton() {
  const button = optional("packButton");
  if (!button) return;
  const active = Boolean(state.activePackJob);
  const lock = currentRunAllLock();
  const runAllActive = Boolean(lock);
  button.disabled = active || runAllActive || document.body.getAttribute("aria-busy") === "true";
  button.textContent = active ? "팩 빌드 중" : runAllActive ? "전체 테스트 진행 중" : "팩 빌드";
  button.title = active
    ? packJobSummary(state.activePackJob)
    : runAllActive
      ? `${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)} 시작`
      : "";
}

function bulkBuildButtons() {
  return [optional("workspaceBuildAllButton"), optional("buildAllPacksButton")].filter(Boolean);
}

function updateBuildAllPacksButton() {
  const buttons = bulkBuildButtons();
  if (!buttons.length) return;
  const active = Boolean(state.activePackJob);
  const lock = currentRunAllLock();
  const runAllActive = Boolean(lock);
  const hasProblems = bulkProblemIds().length > 0;
  for (const button of buttons) {
    button.disabled =
      !hasProblems || active || runAllActive || document.body.getAttribute("aria-busy") === "true";
    button.textContent = active
      ? "팩 빌드 진행 중"
      : runAllActive
        ? "전체 테스트 진행 중"
        : "전체 문제 테스트/팩 빌드";
    button.title = !hasProblems
      ? "등록된 문제가 없습니다."
      : active
        ? packJobSummary(state.activePackJob)
        : runAllActive
          ? `${lock.problemId || "전체 문제"} · ${formatTime(lock.startedAt)} 시작`
          : "모든 문제를 순서대로 테스트하고 통과한 문제 팩을 생성합니다.";
  }
}

function updateGlobalStatus() {
  const status = optional("globalTaskStatus");
  if (!status) return;
  const lock = currentRunAllLock();
  const messages = [];
  if (lock) {
    messages.push(`전체 테스트 진행 중 · ${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)}`);
  }
  if (state.activePackJob) {
    messages.push(`팩 빌드 진행 중 · ${packJobSummary(state.activePackJob)}`);
  }
  status.textContent = messages.join(" / ");
  status.classList.toggle("hidden", !messages.length);
}

function updateGlobalActionState() {
  updateRunAllButton();
  updatePackButton();
  updateBuildAllPacksButton();
  updateGlobalStatus();
}

function formatTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function acquireRunAllLease(problemId = state.selectedProblem) {
  const existing = currentRunAllLock();
  if (existing && existing.owner !== TAB_INSTANCE_ID) return null;
  const lock = {
    owner: TAB_INSTANCE_ID,
    token: window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
    problemId,
    startedAt: Date.now(),
    expiresAt: Date.now() + RUN_ALL_LOCK_TTL_MS,
  };
  writeStorage(RUN_ALL_LOCK_KEY, lock);
  const stored = currentRunAllLock();
  if (!stored || stored.token !== lock.token) return null;
  announceRunAllLock();
  updateGlobalActionState();
  return lock;
}

function releaseRunAllLease(lock) {
  const stored = currentRunAllLock();
  if (stored?.token === lock?.token) {
    removeStorage(RUN_ALL_LOCK_KEY);
    announceRunAllLock();
  }
  updateGlobalActionState();
}

async function withProblemTaskLock(action) {
  if (!navigator.locks?.request) return action();
  return navigator.locks.request(PROBLEM_TASK_LOCK_NAME, { ifAvailable: true }, async (lock) => {
    if (!lock) throw new Error("이미 다른 탭에서 전체 테스트 또는 팩 빌드가 실행 중입니다.");
    return action();
  });
}

async function runAllChecksOnce() {
  if (state.activePackJob) throw new Error("팩 빌드 진행 중에는 전체 테스트를 시작할 수 없습니다.");
  return withProblemTaskLock(async () => {
    const lease = acquireRunAllLease();
    if (!lease) throw new Error("이미 다른 탭에서 전체 테스트가 실행 중입니다.");
    try {
      await saveOpenFileIfDirty();
      return await runAllChecks();
    } finally {
      releaseRunAllLease(lease);
    }
  });
}

function alertTypeFromClass(className = "") {
  if (className.includes("error")) return "error";
  if (className.includes("success")) return "success";
  if (className.includes("warning")) return "warning";
  return "info";
}

function alertTitle(type) {
  if (type === "success") return "완료";
  if (type === "warning") return "주의";
  if (type === "error") return "오류";
  return "알림";
}

function showAlert(message, type = "info", options = {}) {
  const stack = optional("alertStack");
  if (!stack) {
    window.alert(message);
    return;
  }
  const existing = stack.querySelectorAll(".app-alert");
  for (const item of Array.from(existing).slice(0, Math.max(0, existing.length - 3))) {
    item.remove();
  }
  const alert = document.createElement("section");
  alert.className = `app-alert ${type}`;
  alert.setAttribute("role", "alert");

  const body = document.createElement("div");
  body.className = "alert-body";

  const title = document.createElement("strong");
  title.textContent = options.title || alertTitle(type);

  const content = document.createElement("p");
  content.textContent = normalizeErrorDetail(message) || "알 수 없는 문제가 발생했습니다.";

  const close = document.createElement("button");
  close.className = "alert-close";
  close.type = "button";
  close.setAttribute("aria-label", "알림 닫기");
  close.textContent = "×";
  close.addEventListener("click", () => alert.remove());

  body.append(title, content);
  alert.append(body, close);
  stack.appendChild(alert);

  const timeout = options.timeout ?? (type === "error" ? 8000 : 4200);
  if (timeout > 0) {
    window.setTimeout(() => alert.remove(), timeout);
  }
}

function showResult(message, className = "") {
  const type = alertTypeFromClass(className);
  showAlert(message, type, { title: alertTitle(type) });
}

function appendOutput(message) {
  void message;
}

function clearOutput() {
  // Kept for command flows that previously reset command output state.
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function updateProgressAlert(title, steps) {
  if (state.progress.active) return;
  const running = steps.find((step) => step.status === "running");
  const done = steps.filter((step) => step.status === "success").length;
  setText("loadingTitle", title);
  setText("loadingMessage", running ? running.label : `${done}/${steps.length} 완료`);
}

function apiFilePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

function problemLabel(problem) {
  return `${problem.problemId} ${problem.title || ""}`.trim();
}

function folderLabel(folder) {
  return String(folder || "").trim() || "기본";
}

function problemFolderKey(folder) {
  return folderLabel(folder);
}

function isProblemFolderCollapsed(folder) {
  return state.problemFolderCollapsed[problemFolderKey(folder)] === true;
}

function toggleProblemFolder(folder) {
  const key = problemFolderKey(folder);
  if (state.problemFolderCollapsed[key]) {
    delete state.problemFolderCollapsed[key];
  } else {
    state.problemFolderCollapsed[key] = true;
  }
  rememberView();
  renderProblems(state.problems);
}

function problemFolderSummaries(problems) {
  const counts = {};
  for (const problem of problems || []) {
    const folder = String(problem.folder || "").trim();
    counts[folder] = (counts[folder] || 0) + 1;
  }
  return Object.keys(counts)
    .sort((left, right) => {
      const leftDefault = left === "";
      const rightDefault = right === "";
      if (leftDefault !== rightDefault) return leftDefault ? 1 : -1;
      return left.localeCompare(right);
    })
    .map((folder) => ({
      name: folder,
      label: folderLabel(folder),
      problemCount: counts[folder],
    }));
}

function syncWorkspaceProblemSummaries() {
  if (!state.workspace) return;
  state.workspace = {
    ...state.workspace,
    problems: state.problems,
    problemIds: state.problems.map((problem) => problem.problemId),
    problemCount: state.problems.length,
    folders: problemFolderSummaries(state.problems),
  };
  renderWorkspace(state.workspace);
}

function positiveIntegerInput(id, fallback) {
  const value = Number.parseInt($(id).value, 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function textInputValue(id, fallback = "") {
  return $(id).value.trim() || fallback;
}

function safeMetadataPath(value) {
  const path = String(value || "").trim();
  return path && !path.startsWith("/") && !path.split("/").includes("..");
}

function metadataFormIssues() {
  const issues = [];
  const problemId = $("metadataProblemIdInput").value.trim();
  const version = Number.parseInt($("metadataVersion").value, 10);
  if (!problemId) issues.push("문제 번호를 입력하세요.");
  if (problemId && !SAFE_PROBLEM_ID.test(problemId)) {
    issues.push("문제 번호는 영문, 숫자, _, - 만 사용할 수 있습니다.");
  }
  if (!$("metadataTitle").value.trim()) issues.push("제목을 입력하세요.");
  if (!Number.isFinite(version) || version < 1) issues.push("버전은 1 이상의 숫자여야 합니다.");
  if (!$("metadataDefaultProfile").value.trim()) issues.push("기본 프로필을 입력하세요.");
  for (const [id, _key, label] of METADATA_TIMEOUT_FIELDS) {
    const value = Number.parseInt($(id).value, 10);
    if (!Number.isFinite(value) || value < 1) {
      issues.push(`${label}은 1ms 이상의 숫자여야 합니다.`);
    }
  }
  for (const [id, _key, label] of METADATA_TOOL_FIELDS) {
    if (!safeMetadataPath($(id).value)) {
      issues.push(`${label} 경로는 비어 있지 않은 상대 경로여야 합니다.`);
    }
  }
  return issues;
}

function renderMetadataValidation() {
  const panel = optional("metadataValidationSummary");
  if (!panel) return;
  if (state.selectedTab !== "info" || !state.selectedProblem) {
    panel.className = "metadata-validation-summary hidden";
    panel.innerHTML = "";
    return;
  }
  const issues = metadataFormIssues();
  panel.className = `metadata-validation-summary${issues.length ? " error" : ""}`;
  panel.innerHTML = issues.length
    ? `<strong>저장 전에 확인할 항목</strong><ul>${issues
        .map((issue) => `<li>${escapeHtml(issue)}</li>`)
        .join("")}</ul>`
    : "<strong>저장 가능한 설정입니다.</strong>";
}

function metadataRawEditorDirty() {
  return state.selectedFile === "problem.json" && hasUnsavedChanges();
}

function currentMetadataDraft() {
  const existing = state.detail?.metadata || {};
  const existingLimits = existing.limits || {};
  const existingTools = existing.tools || {};
  return {
    title: textInputValue("metadataTitle", "Untitled Problem"),
    folder: textInputValue("metadataFolder"),
    version: positiveIntegerInput("metadataVersion", existing.version || 1),
    defaultProfile: textInputValue("metadataDefaultProfile", "hidden"),
    limits: {
      ...existingLimits,
      compileTimeoutMs: positiveIntegerInput(
        "metadataCompileTimeout",
        existingLimits.compileTimeoutMs || 5000
      ),
      generationTimeoutMs: positiveIntegerInput(
        "metadataGenerationTimeout",
        existingLimits.generationTimeoutMs || 5000
      ),
      solutionTimeoutMs: positiveIntegerInput(
        "metadataSolutionTimeout",
        existingLimits.solutionTimeoutMs || 2000
      ),
      userTimeoutMs: positiveIntegerInput(
        "metadataUserTimeout",
        existingLimits.userTimeoutMs || 2000
      ),
    },
    tools: {
      ...existingTools,
      generator: textInputValue("metadataToolGenerator", "generator/generator.cpp"),
      generatorConfig: textInputValue("metadataToolGeneratorConfig", "generator/cases.yml"),
      validator: textInputValue("metadataToolValidator", "validator/validator.cpp"),
      checker: textInputValue("metadataToolChecker", "checker/judge.cpp"),
      solution: textInputValue("metadataToolSolution", "solutions/main_solution.ac.cpp"),
    },
  };
}

function currentProblemIdDraft() {
  return textInputValue("metadataProblemIdInput", state.selectedProblem || "");
}

function migrateProblemLastResult(previousProblemId, nextProblemId) {
  if (!previousProblemId || !nextProblemId || previousProblemId === nextProblemId) return;
  const results = storedLastResults();
  if (!results[previousProblemId]) return;
  results[nextProblemId] = {
    ...results[previousProblemId],
    problemId: nextProblemId,
    updatedAt: Date.now(),
  };
  delete results[previousProblemId];
  writeStorage(LAST_RESULTS_KEY, results);
}

function migrateTabSelections(previousProblemId, nextProblemId) {
  if (!previousProblemId || !nextProblemId || previousProblemId === nextProblemId) return;
  const migrated = {};
  for (const [key, value] of Object.entries(state.tabSelections || {})) {
    const prefix = `${previousProblemId}:`;
    migrated[key.startsWith(prefix) ? `${nextProblemId}:${key.slice(prefix.length)}` : key] = value;
  }
  state.tabSelections = migrated;
}

function applyProblemRenameResult(result, previousProblemId) {
  const nextProblemId = result.problemId;
  if (!nextProblemId || nextProblemId === previousProblemId) return;
  migrateProblemLastResult(previousProblemId, nextProblemId);
  migrateTabSelections(previousProblemId, nextProblemId);
  if (state.activePackJob?.problemId === previousProblemId) clearPackJob();
  state.selectedProblem = nextProblemId;
  if (state.detail) {
    state.detail = {
      ...state.detail,
      problemId: nextProblemId,
      path: result.path || state.detail.path,
      metadata: result.metadata || state.detail.metadata,
    };
  }
  if (result.workspace) {
    renderWorkspace(result.workspace);
    renderProblems(result.workspace.problems || []);
  }
  rememberView();
}

function applyProblemMetadataToUi(metadata, options = {}) {
  if (!state.selectedProblem || !metadata) return;
  if (state.detail) state.detail.metadata = { ...(state.detail.metadata || {}), ...metadata };
  const problem = state.problems.find((item) => item.problemId === state.selectedProblem);
  if (problem) {
    problem.title = metadata.title || problem.title || "";
    problem.folder = metadata.folder ?? problem.folder ?? "";
    problem.version = metadata.version ?? problem.version;
    problem.defaultProfile = metadata.defaultProfile || problem.defaultProfile;
  }
  const title = `${state.selectedProblem} ${metadata.title || ""}`.trim();
  const meta = `폴더 ${folderLabel(metadata.folder)} · 버전 ${metadata.version ?? "-"} · 기본 프로필 ${
    metadata.defaultProfile || "-"
  }`;
  setText("problemTitle", title);
  setText("problemMeta", meta);
  updateMobileHeader(
    title,
    `${folderLabel(metadata.folder)} · v${metadata.version ?? "-"} · ${metadata.defaultProfile || "-"}`
  );
  syncWorkspaceProblemSummaries();
  renderProblems(state.problems);
  if (options.markDirty) {
    markFullTestDirty("문제 메타데이터가 변경되어 전체 테스트가 다시 필요합니다.");
  }
}

function updateMetadataPreview() {
  if (state.selectedTab !== "info" || !state.selectedProblem) return;
  const metadata = currentMetadataDraft();
  const title = `${state.selectedProblem} ${metadata.title || ""}`.trim();
  const meta = `폴더 ${folderLabel(metadata.folder)} · 버전 ${metadata.version ?? "-"} · 기본 프로필 ${
    metadata.defaultProfile || "-"
  }`;
  setText("problemTitle", title);
  setText("problemMeta", meta);
  updateMobileHeader(
    title,
    `${folderLabel(metadata.folder)} · v${metadata.version ?? "-"} · ${metadata.defaultProfile || "-"}`
  );
  renderMetadataValidation();
}

function languageForPath(path) {
  const lower = (path || "").toLowerCase();
  if (lower.endsWith(".cpp") || lower.endsWith(".cc") || lower.endsWith(".cxx")) return "cpp";
  if (lower.endsWith(".py")) return "python";
  if (lower.endsWith(".java")) return "java";
  if (lower.endsWith(".yml") || lower.endsWith(".yaml")) return "yaml";
  if (lower.endsWith(".json")) return "json";
  return "text";
}

function protectMatches(value, patterns) {
  const placeholders = [];
  let highlighted = value;
  const mark = (content, className) => {
    const token = String.fromCodePoint(0xe000 + placeholders.length);
    placeholders.push({ token, html: `<span class="${className}">${content}</span>` });
    return token;
  };
  for (const { pattern, className, replacer } of patterns) {
    highlighted = highlighted.replace(pattern, (...args) => {
      if (replacer) return replacer(mark, ...args);
      return mark(args[0], className);
    });
  }
  return {
    value: highlighted,
    restore: (text) =>
      placeholders.reduce(
        (output, placeholder) => output.replaceAll(placeholder.token, placeholder.html),
        text
      ),
  };
}

function highlightCode(text, language) {
  const escaped = escapeHtml(text || "");
  if (language === "json") {
    const protectedJson = protectMatches(escaped, [
      {
        pattern: /(&quot;[^&]*?&quot;)(\s*:)/g,
        replacer: (mark, _match, key, colon) => `${mark(key, "tok-key")}${colon}`,
      },
      { pattern: /(&quot;.*?&quot;)/g, className: "tok-string" },
    ]);
    return protectedJson.restore(
      protectedJson.value
      .replace(/\b(true|false|null)\b/g, '<span class="tok-keyword">$1</span>')
        .replace(/\b(-?\d+(?:\.\d+)?)\b/g, '<span class="tok-number">$1</span>')
    );
  }
  if (language === "yaml") {
    const protectedYaml = protectMatches(escaped, [
      { pattern: /^(\s*#.*)$/gm, className: "tok-comment" },
      { pattern: /(&quot;.*?&quot;)/g, className: "tok-string" },
    ]);
    return protectedYaml.restore(
      protectedYaml.value
        .replace(/^(\s*[-]?\s*[A-Za-z0-9_-]+)(:)/gm, '<span class="tok-key">$1</span>$2')
        .replace(/\b(-?\d+)\b/g, '<span class="tok-number">$1</span>')
    );
  }
  if (language === "python") {
    const protectedPython = protectMatches(escaped, [
      { pattern: /^(\s*#.*)$/gm, className: "tok-comment" },
      { pattern: /(&quot;.*?&quot;|'.*?')/g, className: "tok-string" },
    ]);
    return protectedPython.restore(
      protectedPython.value
      .replace(/\b(def|class|if|elif|else|for|while|return|import|from|as|try|except|with|pass|in|and|or|not|None|True|False)\b/g, '<span class="tok-keyword">$1</span>')
        .replace(/\b(-?\d+)\b/g, '<span class="tok-number">$1</span>')
    );
  }
  if (language === "java" || language === "cpp") {
    const protectedCode = protectMatches(escaped, [
      { pattern: /(\/\/.*)$/gm, className: "tok-comment" },
      { pattern: /(&quot;.*?&quot;|'.*?')/g, className: "tok-string" },
    ]);
    return protectedCode.restore(
      protectedCode.value
      .replace(/\b(class|public|private|protected|static|void|int|long|double|float|char|bool|boolean|string|String|return|if|else|for|while|do|switch|case|break|continue|include|using|namespace|std|auto|const|vector|map|set)\b/g, '<span class="tok-keyword">$1</span>')
        .replace(/\b(-?\d+)\b/g, '<span class="tok-number">$1</span>')
    );
  }
  return escaped;
}

function codeMirrorModeForPath(path) {
  const language = languageForPath(path);
  return codeMirrorModeForLanguage(language);
}

function codeMirrorModeForLanguage(language) {
  return {
    cpp: "text/x-c++src",
    java: "text/x-java",
    python: "python",
    json: "application/json",
    yaml: "yaml",
    text: "text/plain",
  }[language] || "text/plain";
}

function normalizeCodeMirrorVimMode(mode) {
  const value = String(mode || "").toLowerCase();
  if (value.includes("insert")) return "insert";
  if (value.includes("visual block")) return "visual-block";
  if (value.includes("visual line")) return "visual-line";
  if (value.includes("visual")) return "visual";
  return "normal";
}

function getEditorValue() {
  return state.codeMirror ? state.codeMirror.getValue() : $("fileEditor").value;
}

function setEditorValue(value, options = {}) {
  const nextValue = value || "";
  state.editorApplyingValue = true;
  $("fileEditor").value = nextValue;
  if (state.codeMirror && state.codeMirror.getValue() !== nextValue) {
    state.codeMirror.setValue(nextValue);
    if (options.clearHistory) state.codeMirror.clearHistory();
  }
  state.editorApplyingValue = false;
  updateEditorVisuals();
}

function focusEditor() {
  if (state.codeMirror) state.codeMirror.focus();
  else $("fileEditor").focus();
}

function editorCursorOffset() {
  if (!state.codeMirror) return $("fileEditor").selectionStart || 0;
  return state.codeMirror.indexFromPos(state.codeMirror.getCursor());
}

function updateCodeMirrorOptions() {
  if (!state.codeMirror) return;
  const nextMode = codeMirrorModeForPath(state.selectedFile);
  const nextKeyMap = state.editorMode === "vim" ? "vim" : "default";
  if (state.codeMirror.getOption("mode") !== nextMode) {
    state.codeMirror.setOption("mode", nextMode);
  }
  if (state.codeMirror.getOption("keyMap") !== nextKeyMap) {
    state.codeMirror.setOption("keyMap", nextKeyMap);
  }
  window.requestAnimationFrame(() => state.codeMirror?.refresh());
  updateModalEditorOptions();
}

function nextWordEndIndex(value, position) {
  let cursor = Math.max(0, Math.min(position + 1, value.length));
  while (cursor < value.length && /\s/.test(value[cursor])) cursor += 1;
  while (cursor < value.length && /\w/.test(value[cursor])) cursor += 1;
  return Math.max(0, Math.min(value.length, cursor - 1));
}

function moveCodeMirrorCursorToIndex(index) {
  if (!state.codeMirror) return;
  const cursor = state.codeMirror.posFromIndex(Math.max(0, Math.min(index, state.codeMirror.getValue().length)));
  state.codeMirror.setCursor(cursor);
  state.codeMirror.scrollIntoView(cursor, 48);
  updateEditorStatus();
}

function handleCodeMirrorVimFallback(event) {
  if (!state.codeMirror || state.editorMode !== "vim" || state.vimMode !== "normal") return false;
  if (event.metaKey || event.ctrlKey || event.altKey || event.isComposing || event.keyCode === 229) return false;
  const key = event.key;
  const cursor = state.codeMirror.getCursor();
  const value = state.codeMirror.getValue();
  const offset = state.codeMirror.indexFromPos(cursor);
  const prevent = () => {
    event.preventDefault();
    event.stopPropagation();
  };
  if (state.codeMirrorPendingKey === "g") {
    state.codeMirrorPendingKey = "";
    if (key === "g") {
      prevent();
      state.codeMirror.setCursor({ line: 0, ch: 0 });
      state.codeMirror.scrollIntoView({ line: 0, ch: 0 }, 48);
      return true;
    }
  }
  if (key === "g") {
    prevent();
    state.codeMirrorPendingKey = "g";
    return true;
  }
  state.codeMirrorPendingKey = "";
  if (key === "k" || key === "ArrowUp") {
    prevent();
    state.codeMirror.setCursor({
      line: Math.max(0, cursor.line - 1),
      ch: cursor.ch,
    });
    state.codeMirror.scrollIntoView(state.codeMirror.getCursor(), 48);
    return true;
  }
  if (key === "j" || key === "ArrowDown") {
    prevent();
    state.codeMirror.setCursor({
      line: Math.min(state.codeMirror.lineCount() - 1, cursor.line + 1),
      ch: cursor.ch,
    });
    state.codeMirror.scrollIntoView(state.codeMirror.getCursor(), 48);
    return true;
  }
  if (key === "h" || key === "ArrowLeft") {
    prevent();
    moveCodeMirrorCursorToIndex(offset - 1);
    return true;
  }
  if (key === "l" || key === "ArrowRight") {
    prevent();
    moveCodeMirrorCursorToIndex(offset + 1);
    return true;
  }
  if (key === "e") {
    prevent();
    moveCodeMirrorCursorToIndex(nextWordEndIndex(value, offset));
    return true;
  }
  if (key === "w") {
    prevent();
    moveCodeMirrorCursorToIndex(nextWordPosition(value, offset));
    return true;
  }
  if (key === "b") {
    prevent();
    moveCodeMirrorCursorToIndex(previousWordPosition(value, offset));
    return true;
  }
  if (key === "0" || key === "Home") {
    prevent();
    state.codeMirror.setCursor({ line: cursor.line, ch: 0 });
    return true;
  }
  if (key === "^") {
    prevent();
    const line = state.codeMirror.getLine(cursor.line) || "";
    const first = line.search(/\S/);
    state.codeMirror.setCursor({ line: cursor.line, ch: first < 0 ? 0 : first });
    return true;
  }
  if (key === "$" || key === "End") {
    prevent();
    state.codeMirror.setCursor({ line: cursor.line, ch: (state.codeMirror.getLine(cursor.line) || "").length });
    return true;
  }
  if (key === "G") {
    prevent();
    const line = state.codeMirror.lineCount() - 1;
    state.codeMirror.setCursor({ line, ch: 0 });
    state.codeMirror.scrollIntoView({ line, ch: 0 }, 48);
    return true;
  }
  return false;
}

function handleCodeMirrorBeforeChange(_instance, change) {
  if (state.editorApplyingValue) return;
  const blocksTextInput = state.editorMode === "vim" && state.vimMode !== "insert";
  const origin = String(change.origin || "");
  if (blocksTextInput && (origin === "+input" || origin === "paste" || /compose/i.test(origin))) {
    change.cancel();
  }
}

function handleCodeMirrorBeforeInput(event) {
  const wrapperMode = event.target?.closest?.(".CodeMirror")?.dataset?.vimMode;
  const activeMode = wrapperMode || state.vimMode;
  if (state.editorMode === "vim" && activeMode !== "insert") {
    event.preventDefault();
  }
}

function stopVimEscapeFromClosingModal(event) {
  if (event.key === "Escape" && state.editorMode === "vim") {
    event.stopPropagation();
  }
}

function handleCodeMirrorChange(instance) {
  if (state.editorApplyingValue) return;
  $("fileEditor").value = instance.getValue();
  handleEditorInput();
}

function initializeCodeMirror() {
  if (state.codeMirror || !window.CodeMirror) return;
  const editor = $("fileEditor");
  const cm = window.CodeMirror.fromTextArea(editor, {
    lineNumbers: true,
    mode: codeMirrorModeForPath(state.selectedFile),
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    lineWrapping: false,
    keyMap: state.editorMode === "vim" ? "vim" : "default",
    showCursorWhenSelecting: true,
    extraKeys: {
      Tab: (instance) => {
        if (instance.somethingSelected()) instance.indentSelection("add");
        else instance.replaceSelection(EDITOR_INDENT, "end");
      },
      "Shift-Tab": (instance) => instance.indentSelection("subtract"),
      "Ctrl-S": () => void withErrors(saveFile, "파일을 저장하는 중입니다."),
      "Cmd-S": () => void withErrors(saveFile, "파일을 저장하는 중입니다."),
    },
  });
  state.codeMirror = cm;
  cm.on("beforeChange", handleCodeMirrorBeforeChange);
  cm.on("change", handleCodeMirrorChange);
  cm.on("cursorActivity", () => {
    updateEditorStatus();
    if (state.editorMode === "vim") cm.scrollIntoView(cm.getCursor(), 48);
  });
  cm.on("scroll", updateEditorStatus);
  window.CodeMirror.on(cm, "vim-mode-change", (event) => {
    state.vimMode = normalizeCodeMirrorVimMode(event?.mode);
    updateEditorSettingsUi();
  });
  if (window.CodeMirror.Vim?.defineEx) {
    window.CodeMirror.Vim.defineEx("write", "w", () => {
      void withErrors(saveFile, "파일을 저장하는 중입니다.");
    });
  }
  const wrapper = cm.getWrapperElement();
  wrapper.classList.add("studio-codemirror");
  wrapper.addEventListener("beforeinput", handleCodeMirrorBeforeInput, true);
  wrapper.addEventListener("compositionstart", handleEditorCompositionStart, true);
  wrapper.addEventListener("compositionend", handleEditorCompositionEnd, true);
  updateCodeMirrorOptions();
}

function modalEditorKeyMap() {
  return state.editorMode === "vim" ? "vim" : "default";
}

function modalEditorKeyForElement(element) {
  const modal = element?.closest?.("#solutionCreateModal, #solutionEditModal");
  if (modal?.id === "solutionCreateModal") return "create";
  if (modal?.id === "solutionEditModal") return "edit";
  return "";
}

function focusModalEditor(key) {
  const editor = state.modalEditors[key];
  if (!editor) return;
  window.requestAnimationFrame(() => {
    editor.refresh();
    editor.focus();
  });
}

function modalEditorLanguage(key) {
  return optional(key === "create" ? "solutionCreateLanguage" : "solutionLanguage")?.value || "cpp";
}

function syncModalEditorMode(key) {
  const editor = state.modalEditors[key];
  if (!editor) return;
  const language = modalEditorLanguage(key);
  const nextMode = codeMirrorModeForLanguage(language);
  if (editor.getOption("mode") !== nextMode) {
    editor.setOption("mode", nextMode);
  }
  editor.getWrapperElement().dataset.language = language;
}

function initializeSourceModalEditors() {
  if (!window.CodeMirror) return;
  const configs = [
    {
      key: "create",
      textareaId: "solutionCreateSource",
      languageId: "solutionCreateLanguage",
      save: () => void withErrors(createSolution, "솔루션 파일을 생성하는 중입니다."),
    },
    {
      key: "edit",
      textareaId: "solutionEditSource",
      languageId: "solutionLanguage",
      save: () => void withErrors(renameSolution, "솔루션 파일명을 변경하는 중입니다."),
    },
  ];
  for (const config of configs) {
    if (state.modalEditors[config.key]) continue;
    const textarea = optional(config.textareaId);
    if (!textarea) continue;
    const cm = window.CodeMirror.fromTextArea(textarea, {
      lineNumbers: true,
      mode: codeMirrorModeForLanguage(optional(config.languageId)?.value || "cpp"),
      indentUnit: 4,
      tabSize: 4,
      indentWithTabs: false,
      lineWrapping: false,
      keyMap: modalEditorKeyMap(),
      extraKeys: {
        Tab: (instance) => {
          if (instance.somethingSelected()) instance.indentSelection("add");
          else instance.replaceSelection(EDITOR_INDENT, "end");
        },
        "Shift-Tab": (instance) => instance.indentSelection("subtract"),
        "Ctrl-S": config.save,
        "Cmd-S": config.save,
      },
    });
    cm.on("cursorActivity", () => {
      if (state.editorMode === "vim") cm.scrollIntoView(cm.getCursor(), 48);
    });
    window.CodeMirror.on(cm, "vim-mode-change", (event) => {
      const wrapper = cm.getWrapperElement();
      const nextMode = normalizeCodeMirrorVimMode(event?.mode);
      wrapper.dataset.editorMode = state.editorMode;
      wrapper.dataset.vimMode = nextMode;
      state.vimMode = nextMode;
      updateEditorSettingsUi();
    });
    const wrapper = cm.getWrapperElement();
    wrapper.classList.add("source-modal-codemirror", "studio-codemirror");
    wrapper.addEventListener("beforeinput", handleCodeMirrorBeforeInput, true);
    wrapper.addEventListener("keydown", stopVimEscapeFromClosingModal);
    state.modalEditors[config.key] = cm;
  }
  updateModalEditorOptions();
}

function updateModalEditorOptions() {
  const createEditor = state.modalEditors.create;
  const editEditor = state.modalEditors.edit;
  if (createEditor) {
    createEditor.setOption("keyMap", modalEditorKeyMap());
    syncModalEditorMode("create");
    const wrapper = createEditor.getWrapperElement();
    const previousMode = wrapper.dataset.editorMode;
    wrapper.dataset.editorMode = state.editorMode;
    wrapper.dataset.vimMode =
      state.editorMode === "vim" ? (previousMode === "vim" ? wrapper.dataset.vimMode || "normal" : "normal") : "insert";
  }
  if (editEditor) {
    editEditor.setOption("keyMap", modalEditorKeyMap());
    syncModalEditorMode("edit");
    const wrapper = editEditor.getWrapperElement();
    const previousMode = wrapper.dataset.editorMode;
    wrapper.dataset.editorMode = state.editorMode;
    wrapper.dataset.vimMode =
      state.editorMode === "vim" ? (previousMode === "vim" ? wrapper.dataset.vimMode || "normal" : "normal") : "insert";
  }
  window.requestAnimationFrame(() => {
    createEditor?.refresh();
    editEditor?.refresh();
  });
}

function getModalEditorValue(key) {
  if (state.modalEditors[key]) return state.modalEditors[key].getValue();
  return optional(key === "create" ? "solutionCreateSource" : "solutionEditSource")?.value || "";
}

function setModalEditorValue(key, value) {
  const textareaId = key === "create" ? "solutionCreateSource" : "solutionEditSource";
  const textarea = optional(textareaId);
  if (textarea) textarea.value = value || "";
  const editor = state.modalEditors[key];
  if (editor) {
    editor.setValue(value || "");
    editor.clearHistory();
    syncModalEditorMode(key);
  }
  window.requestAnimationFrame(() => state.modalEditors[key]?.refresh());
}

function refreshModalEditor(key) {
  const editor = state.modalEditors[key];
  if (!editor) return;
  syncModalEditorMode(key);
  window.requestAnimationFrame(() => {
    editor.refresh();
    window.requestAnimationFrame(() => editor.refresh());
  });
}

function updateEditorVisuals() {
  if (state.codeMirror) {
    updateCodeMirrorOptions();
    updateEditorStatus();
    return;
  }
  const editor = $("fileEditor");
  const language = languageForPath(state.selectedFile);
  $("codeEditor").dataset.language = language;
  const text = editor.value || "";
  $("codeHighlight").innerHTML = highlightCode(text, language) + "\n";
  const lineCount = Math.max(1, text.split("\n").length);
  $("editorLineNumbers").textContent = Array.from({ length: lineCount }, (_, index) => index + 1).join("\n");
  syncEditorScroll();
  updateEditorStatus();
}

function syncEditorScroll() {
  if (state.codeMirror) return;
  const editor = $("fileEditor");
  $("codeHighlight").scrollTop = editor.scrollTop;
  $("codeHighlight").scrollLeft = editor.scrollLeft;
  $("editorLineNumbers").scrollTop = editor.scrollTop;
}

function ensureEditorCursorVisible(editor) {
  if (state.codeMirror) {
    state.codeMirror.scrollIntoView(state.codeMirror.getCursor(), 48);
    return;
  }
  const cursorPosition = isVimVisualMode()
    ? state.vimVisualCursor ?? editor.selectionStart
    : editor.selectionStart;
  const { line, column } = editorLineColumn(editor.value || "", cursorPosition || 0);
  const styles = window.getComputedStyle(editor);
  const lineHeight = Number.parseFloat(styles.lineHeight) || 20;
  const fontSize = Number.parseFloat(styles.fontSize) || 13;
  const charWidth = fontSize * 0.62;
  const targetTop = Math.max(0, (line - 1) * lineHeight);
  const visibleBottom = editor.scrollTop + editor.clientHeight;
  if (targetTop < editor.scrollTop) {
    editor.scrollTop = Math.max(0, targetTop - lineHeight);
  } else if (targetTop + lineHeight > visibleBottom) {
    editor.scrollTop = Math.max(0, targetTop - editor.clientHeight + lineHeight * 2);
  }
  const targetLeft = Math.max(0, column * charWidth);
  const visibleRight = editor.scrollLeft + editor.clientWidth;
  if (targetLeft < editor.scrollLeft) {
    editor.scrollLeft = Math.max(0, targetLeft - charWidth * 2);
  } else if (targetLeft + charWidth > visibleRight) {
    editor.scrollLeft = Math.max(0, targetLeft - editor.clientWidth + charWidth * 4);
  }
  syncEditorScroll();
}

function languageLabelForPath(path) {
  const language = languageForPath(path);
  return {
    cpp: "C++",
    python: "Python",
    java: "Java",
    json: "JSON",
    yaml: "YAML",
    text: "Text",
  }[language] || "Text";
}

function commandStatusText() {
  if (state.editorMode !== "vim") return "";
  const count = state.vimCount ? state.vimCount : "";
  const pending = state.vimPending ? `${state.vimPending}...` : "";
  const visual = isVimVisualMode() ? "visual selection" : "";
  const prefix = [count, pending].filter(Boolean).join(" ");
  return [prefix, visual, state.vimMessage].filter(Boolean).join(" · ");
}

function updateEditorStatus() {
  const editor = optional("fileEditor");
  if (!editor) return;
  const value = getEditorValue();
  const cursorPosition = state.codeMirror
    ? editorCursorOffset()
    : isVimVisualMode()
      ? state.vimVisualCursor ?? editor.selectionStart
      : editor.selectionStart;
  const position = editorLineColumn(value || "", cursorPosition || 0);
  const mode = state.editorMode === "vim" ? editorModeBadgeText() : "기본";
  const dirty = state.selectedFile && value !== state.lastSavedContent ? "수정됨" : "저장됨";
  const percent =
    value.length > 0
      ? `${Math.round(((cursorPosition || 0) / value.length) * 100)}%`
      : "0%";
  setText("editorStatusMode", mode);
  setText("editorStatusPosition", `${dirty} · Ln ${position.line}, Col ${position.column + 1}`);
  setText("editorStatusCommand", commandStatusText());
  setText("editorStatusSearch", state.vimSearchQuery ? `/${state.vimSearchQuery}` : "");
  setText("editorStatusFile", `${languageLabelForPath(state.selectedFile)} · 4 spaces · ${percent}`);
  const statusMode = optional("editorStatusMode");
  if (statusMode) {
    statusMode.className = `editor-status-mode ${
      state.editorMode === "vim" ? `vim-${vimModeClassName()}` : ""
    }`.trim();
  }
}

function lineStartAt(value, position) {
  return value.lastIndexOf("\n", Math.max(0, position - 1)) + 1;
}

function lineEndAt(value, position) {
  const nextBreak = value.indexOf("\n", position);
  return nextBreak === -1 ? value.length : nextBreak;
}

function firstTextColumn(value, lineStart, lineEnd = lineEndAt(value, lineStart)) {
  const match = value.slice(lineStart, lineEnd).match(/\S/);
  return match ? lineStart + match.index : lineStart;
}

function currentLineIndent(value, position) {
  const lineStart = lineStartAt(value, position);
  const lineEnd = lineEndAt(value, position);
  return value.slice(lineStart, firstTextColumn(value, lineStart, lineEnd));
}

function normalLineCursorEnd(value, lineStart) {
  const lineEnd = lineEndAt(value, lineStart);
  return lineEnd > lineStart ? lineEnd - 1 : lineStart;
}

function clampNormalCursor(value, position) {
  if (!value) return 0;
  let bounded = Math.max(0, Math.min(position, value.length - 1));
  const lineStart = lineStartAt(value, bounded);
  const lineEnd = lineEndAt(value, bounded);
  if (bounded >= lineEnd && lineEnd > lineStart) bounded = lineEnd - 1;
  if (value[bounded] === "\n" && lineEnd > lineStart) bounded = lineEnd - 1;
  return Math.max(lineStart, bounded);
}

function normalCursorEndAt(value, position) {
  return normalLineCursorEnd(value, lineStartAt(value, position));
}

function isVimVisualMode(mode = state.vimMode) {
  return mode === "visual" || mode === "visual-line" || mode === "visual-block";
}

function vimModeClassName() {
  return isVimVisualMode() ? "visual" : state.vimMode;
}

function clearVimVisualState() {
  state.vimVisualAnchor = null;
  state.vimVisualCursor = null;
}

function visualSelectionRange(editor) {
  const anchor = state.vimVisualAnchor ?? editor.selectionStart;
  const cursor = state.vimVisualCursor ?? editor.selectionStart;
  if (state.vimMode === "visual-line") {
    const startLine = Math.min(anchor, cursor);
    const endLine = Math.max(anchor, cursor);
    const start = lineStartAt(editor.value, startLine);
    const end = lineWithBreakBounds(editor.value, endLine).end;
    return { start, end };
  }
  const start = Math.min(anchor, cursor);
  const end = Math.min(editor.value.length, Math.max(anchor, cursor) + 1);
  return { start, end };
}

function updateVisualSelection(editor) {
  const { start, end } = visualSelectionRange(editor);
  editor.selectionStart = start;
  editor.selectionEnd = Math.max(start, end);
  ensureEditorCursorVisible(editor);
  updateEditorStatus();
}

function enterVimVisualMode(editor, mode = "visual") {
  state.vimMode = mode === "visual-line" ? "visual-line" : "visual";
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  const anchor = clampNormalCursor(editor.value, editor.selectionStart);
  state.vimVisualAnchor = anchor;
  state.vimVisualCursor = anchor;
  updateVisualSelection(editor);
  updateEditorSettingsUi();
}

function exitVimVisualMode(editor) {
  const cursor = state.vimVisualCursor ?? editor.selectionStart;
  state.vimMode = "normal";
  clearVimVisualState();
  moveEditorCursor(editor, cursor);
  updateEditorSettingsUi();
}

function moveEditorCursor(editor, position, preferredColumn = null, options = {}) {
  const shouldClamp =
    options.normal !== false
    && state.editorMode === "vim"
    && (state.vimMode === "normal" || isVimVisualMode());
  const bounded = shouldClamp
    ? clampNormalCursor(editor.value, position)
    : Math.max(0, Math.min(position, editor.value.length));
  if (state.editorMode === "vim" && isVimVisualMode()) {
    state.vimVisualCursor = bounded;
    state.vimPreferredColumn = preferredColumn;
    updateVisualSelection(editor);
    return;
  }
  editor.selectionStart = bounded;
  editor.selectionEnd = bounded;
  state.vimPreferredColumn = preferredColumn;
  ensureEditorCursorVisible(editor);
  updateEditorStatus();
}

function editorLineColumn(value, position) {
  const lineStart = lineStartAt(value, position);
  const line = value.slice(0, position).split("\n").length;
  return { lineStart, line, column: position - lineStart };
}

function activeEditorCursor(editor) {
  return isVimVisualMode() ? state.vimVisualCursor ?? editor.selectionStart : editor.selectionStart;
}

function moveEditorVertical(editor, direction) {
  const value = editor.value;
  const cursor = activeEditorCursor(editor);
  const { lineStart, column } = editorLineColumn(value, cursor);
  const preferredColumn = state.vimPreferredColumn ?? column;
  let targetLineStart;
  if (direction > 0) {
    const nextBreak = value.indexOf("\n", lineStart);
    if (nextBreak < 0) return;
    targetLineStart = nextBreak + 1;
  } else {
    if (lineStart === 0) return;
    targetLineStart = lineStartAt(value, lineStart - 1);
  }
  if (targetLineStart === lineStart) return;
  const targetLineEnd = state.editorMode === "vim" && state.vimMode === "normal"
    ? normalLineCursorEnd(value, targetLineStart)
    : lineEndAt(value, targetLineStart);
  moveEditorCursor(editor, Math.min(targetLineStart + preferredColumn, targetLineEnd), preferredColumn);
}

function moveEditorHorizontal(editor, amount) {
  const value = editor.value;
  const selectionStart = activeEditorCursor(editor);
  const lineStart = lineStartAt(value, selectionStart);
  const lineEnd = state.editorMode === "vim" && state.vimMode === "normal"
    ? normalLineCursorEnd(value, lineStart)
    : lineEndAt(value, selectionStart);
  moveEditorCursor(editor, Math.max(lineStart, Math.min(selectionStart + amount, lineEnd)));
}

function editorSnapshot(editor) {
  return {
    value: editor.value,
    selectionStart: editor.selectionStart,
    selectionEnd: editor.selectionEnd,
  };
}

function restoreEditorSnapshot(editor, snapshot) {
  editor.value = snapshot.value;
  editor.selectionStart = Math.min(snapshot.selectionStart, editor.value.length);
  editor.selectionEnd = Math.min(snapshot.selectionEnd, editor.value.length);
  updateEditorVisuals();
  updateDirtyState();
}

function resetEditorHistory() {
  state.editorUndoStack = [];
  state.editorRedoStack = [];
}

function pushEditorHistory(editor) {
  const snapshot = editorSnapshot(editor);
  const previous = state.editorUndoStack[state.editorUndoStack.length - 1];
  if (previous && previous.value === snapshot.value && previous.selectionStart === snapshot.selectionStart) {
    return;
  }
  state.editorUndoStack.push(snapshot);
  if (state.editorUndoStack.length > EDITOR_HISTORY_LIMIT) state.editorUndoStack.shift();
  state.editorRedoStack = [];
}

function undoEditorChange(editor) {
  const snapshot = state.editorUndoStack.pop();
  if (!snapshot) {
    state.vimMessage = "되돌릴 변경이 없습니다";
    updateEditorSettingsUi();
    return;
  }
  state.editorRedoStack.push(editorSnapshot(editor));
  restoreEditorSnapshot(editor, snapshot);
  state.vimMessage = "undo";
  if (state.editorMode === "vim" && state.vimMode === "normal") {
    moveEditorCursor(editor, editor.selectionStart);
  }
  updateEditorSettingsUi();
}

function redoEditorChange(editor) {
  const snapshot = state.editorRedoStack.pop();
  if (!snapshot) {
    state.vimMessage = "다시 실행할 변경이 없습니다";
    updateEditorSettingsUi();
    return;
  }
  state.editorUndoStack.push(editorSnapshot(editor));
  restoreEditorSnapshot(editor, snapshot);
  state.vimMessage = "redo";
  if (state.editorMode === "vim" && state.vimMode === "normal") {
    moveEditorCursor(editor, editor.selectionStart);
  }
  updateEditorSettingsUi();
}

function replaceEditorRange(editor, start, end, replacement, cursorPosition = start + replacement.length) {
  pushEditorHistory(editor);
  editor.setRangeText(replacement, start, end, "end");
  moveEditorCursor(editor, cursorPosition);
  updateEditorVisuals();
  updateDirtyState();
}

function setEditorMode(mode, options = {}) {
  state.editorMode = mode === "vim" ? "vim" : "default";
  state.vimMode = state.editorMode === "vim" ? "normal" : "insert";
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  state.vimMessage = "";
  state.vimPreferredColumn = null;
  clearVimVisualState();
  writeStorage(EDITOR_SETTINGS_KEY, { mode: state.editorMode });
  if (state.codeMirror) {
    updateCodeMirrorOptions();
  } else if (state.editorMode === "vim") {
    moveEditorCursor($("fileEditor"), $("fileEditor").selectionStart);
  }
  updateModalEditorOptions();
  updateEditorSettingsUi();
  if (options.modalEditorKey) {
    focusModalEditor(options.modalEditorKey);
  } else if (options.focus !== false) {
    focusEditor();
  }
}

function setVimMode(mode, editor = optional("fileEditor"), options = {}) {
  if (state.editorMode !== "vim") return;
  state.vimMode = mode === "insert" || isVimVisualMode(mode) ? mode : "normal";
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  state.vimPreferredColumn = null;
  if (!isVimVisualMode()) clearVimVisualState();
  if (editor) {
    if (state.vimMode === "insert" && options.recordHistory !== false) {
      pushEditorHistory(editor);
    }
    if (state.vimMode === "normal") {
      const lineStart = lineStartAt(editor.value, editor.selectionStart);
      const position = options.fromInsert && editor.selectionStart > lineStart
        ? editor.selectionStart - 1
        : editor.selectionStart;
      moveEditorCursor(editor, position);
    } else if (isVimVisualMode()) {
      enterVimVisualMode(editor, state.vimMode);
    }
  }
  updateEditorSettingsUi();
}

function editorModeBadgeText() {
  if (state.editorMode !== "vim") return "기본";
  if (state.vimMode === "visual") return "VISUAL";
  if (state.vimMode === "visual-line") return "V-LINE";
  return state.vimMode === "insert" ? "INSERT" : "NORMAL";
}

function updateEditorSettingsUi() {
  const isVim = state.editorMode === "vim";
  for (const button of document.querySelectorAll("[data-editor-mode]")) {
    const active = button.dataset.editorMode === state.editorMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  }
  optional("editorSettingsButton")?.setAttribute(
    "aria-expanded",
    state.editorSettingsOpen ? "true" : "false"
  );
  optional("editorSettingsPanel")?.classList.toggle("hidden", !state.editorSettingsOpen);
  const badge = optional("editorModeBadge");
  if (badge) {
    badge.textContent = editorModeBadgeText();
    badge.className = `editor-mode-badge ${
      isVim ? (state.vimMode === "insert" ? "vim-insert" : `vim-${vimModeClassName()}`) : ""
    }`.trim();
  }
  const codeEditor = optional("codeEditor");
  if (codeEditor) {
    codeEditor.dataset.editorMode = state.editorMode;
    codeEditor.dataset.vimMode = state.vimMode;
  }
  updateEditorStatus();
}

function setEditorSettingsOpen(open) {
  state.editorSettingsOpen = open;
  updateEditorSettingsUi();
}

function restoreEditorSettings() {
  const saved = readStorage(EDITOR_SETTINGS_KEY);
  state.editorMode = saved?.mode === "vim" ? "vim" : "default";
  state.vimMode = state.editorMode === "vim" ? "normal" : "insert";
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  state.vimMessage = "";
  clearVimVisualState();
  state.editorSettingsOpen = false;
  updateCodeMirrorOptions();
  updateEditorSettingsUi();
}

function resetVimTransientState() {
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  state.vimPreferredColumn = null;
  state.vimMessage = "";
  clearVimVisualState();
  closeEditorCommandLine();
  if (state.editorMode === "vim") state.vimMode = "normal";
  updateEditorSettingsUi();
}

function openEditorCommandLine(mode) {
  state.editorCommandMode = mode;
  const panel = optional("editorCommandLine");
  const input = optional("editorCommandInput");
  setText("editorCommandPrefix", mode === "search" ? "/" : ":");
  panel?.classList.remove("hidden");
  if (input) {
    input.value = "";
    input.focus();
  }
}

function closeEditorCommandLine() {
  state.editorCommandMode = "";
  optional("editorCommandLine")?.classList.add("hidden");
  const input = optional("editorCommandInput");
  if (input) input.value = "";
}

function submitEditorCommandLine() {
  const input = optional("editorCommandInput");
  const editor = optional("fileEditor");
  if (!input || !editor) return;
  const value = input.value.trim();
  const mode = state.editorCommandMode;
  closeEditorCommandLine();
  editor.focus();
  if (!value) return;
  if (mode === "search") {
    state.vimSearchQuery = value;
    state.vimSearchDirection = 1;
    findVimSearch(editor, 1, true);
    return;
  }
  if (value === "w" || value === "write") {
    void withErrors(saveFile, "파일을 저장하는 중입니다.");
    state.vimMessage = "write";
  } else {
    state.vimMessage = `지원하지 않는 명령: ${value}`;
  }
  updateEditorSettingsUi();
}

function currentLineBounds(value, position) {
  const start = lineStartAt(value, position);
  const end = lineEndAt(value, position);
  return { start, end };
}

function lineStartByNumber(value, lineNumber) {
  if (lineNumber <= 1) return 0;
  let position = 0;
  for (let line = 1; line < lineNumber; line += 1) {
    const next = value.indexOf("\n", position);
    if (next === -1) return value.length;
    position = next + 1;
  }
  return position;
}

function totalLineCount(value) {
  return Math.max(1, value.split("\n").length);
}

function currentLineNumber(value, position) {
  return value.slice(0, position).split("\n").length;
}

function lineWithBreakBounds(value, position) {
  let { start, end } = currentLineBounds(value, position);
  if (end < value.length) {
    end += 1;
  } else if (start > 0) {
    start -= 1;
  }
  return { start, end };
}

function lineRangeWithBreakBounds(value, position, count = 1) {
  let start = lineStartAt(value, position);
  let end = start;
  for (let index = 0; index < count; index += 1) {
    end = lineEndAt(value, end);
    if (end < value.length) {
      end += 1;
    } else {
      break;
    }
  }
  return { start, end };
}

function nextWordPosition(value, position) {
  const rest = value.slice(Math.min(position + 1, value.length));
  const match = rest.match(/\b\w/);
  return match ? position + 1 + match.index : position;
}

function previousWordPosition(value, position) {
  const before = value.slice(0, Math.max(0, position));
  const matches = [...before.matchAll(/\b\w/g)];
  return matches.length ? matches[matches.length - 1].index || 0 : position;
}

function moveToNextWord(editor, count = 1) {
  let position = activeEditorCursor(editor);
  for (let index = 0; index < count; index += 1) {
    const next = nextWordPosition(editor.value, position);
    if (next === position) break;
    position = next;
  }
  moveEditorCursor(editor, position);
}

function moveToWordEnd(editor, count = 1) {
  let position = activeEditorCursor(editor);
  for (let index = 0; index < count; index += 1) {
    const next = nextWordEndIndex(editor.value, position);
    if (next === position) break;
    position = next;
  }
  moveEditorCursor(editor, position);
}

function moveToPreviousWord(editor, count = 1) {
  let position = activeEditorCursor(editor);
  for (let index = 0; index < count; index += 1) {
    const previous = previousWordPosition(editor.value, position);
    if (previous === position) break;
    position = previous;
  }
  moveEditorCursor(editor, position);
}

function moveToLine(editor, lineNumber) {
  const targetLine = Math.max(1, Math.min(lineNumber, totalLineCount(editor.value)));
  const start = lineStartByNumber(editor.value, targetLine);
  moveEditorCursor(editor, firstTextColumn(editor.value, start, lineEndAt(editor.value, start)));
}

function insertVimLine(editor, above) {
  const { value, selectionStart } = editor;
  const { start, end } = currentLineBounds(value, selectionStart);
  const indent = currentLineIndent(value, selectionStart);
  if (above) {
    const text = `${indent}\n`;
    replaceEditorRange(editor, start, start, text, start + indent.length);
  } else {
    const text = `\n${indent}`;
    replaceEditorRange(editor, end, end, text, end + text.length);
  }
  setVimMode("insert", editor, { recordHistory: false });
}

function deleteVimChar(editor) {
  const { value, selectionStart } = editor;
  if (selectionStart >= value.length || value[selectionStart] === "\n") return;
  state.vimRegister = value.slice(selectionStart, selectionStart + 1);
  state.vimRegisterType = "char";
  replaceEditorRange(editor, selectionStart, selectionStart + 1, "", selectionStart);
}

function replaceVimChar(editor, value) {
  if (!value || value.length !== 1) return;
  const { selectionStart } = editor;
  if (editor.value[selectionStart] === "\n" || selectionStart >= editor.value.length) return;
  replaceEditorRange(editor, selectionStart, selectionStart + 1, value, selectionStart);
  state.vimMessage = `replaced with ${value}`;
}

function deleteVimLine(editor, count = 1, enterInsert = false) {
  const { value, selectionStart } = editor;
  const { start, end } = lineRangeWithBreakBounds(value, selectionStart, count);
  state.vimRegister = value.slice(start, end);
  state.vimRegisterType = "line";
  replaceEditorRange(editor, start, end, "", start);
  state.vimMessage = `${count} line${count > 1 ? "s" : ""} deleted`;
  if (enterInsert) setVimMode("insert", editor, { recordHistory: false });
}

function copyVimLine(editor, count = 1) {
  const { value, selectionStart } = editor;
  const { start, end } = lineRangeWithBreakBounds(value, selectionStart, count);
  state.vimRegister = value.slice(start, end);
  state.vimRegisterType = "line";
  state.vimMessage = `${count} line${count > 1 ? "s" : ""} yanked`;
}

function pasteVimRegister(editor, before = false, count = 1) {
  if (!state.vimRegister) return;
  const { value, selectionStart } = editor;
  if (state.vimRegisterType === "line") {
    const insertAt = before ? lineStartAt(value, selectionStart) : lineEndAt(value, selectionStart);
    const text = state.vimRegister.endsWith("\n")
      ? state.vimRegister.slice(0, -1)
      : state.vimRegister;
    const repeated = Array.from({ length: count }, () => text).join("\n");
    const insertion = before ? `${repeated}\n` : `\n${repeated}`;
    replaceEditorRange(editor, insertAt, insertAt, insertion, insertAt + (before ? 0 : 1));
    state.vimMessage = "pasted";
    return;
  }
  const insertAt = before ? selectionStart : Math.min(selectionStart + 1, value.length);
  const repeated = state.vimRegister.repeat(count);
  replaceEditorRange(editor, insertAt, insertAt, repeated, insertAt + repeated.length - 1);
  state.vimMessage = "pasted";
}

function deleteVimRange(editor, start, end, enterInsert = false) {
  const rangeStart = Math.max(0, Math.min(start, end));
  const rangeEnd = Math.max(rangeStart, Math.max(start, end));
  if (rangeStart === rangeEnd) return;
  state.vimRegister = editor.value.slice(rangeStart, rangeEnd);
  state.vimRegisterType = "char";
  replaceEditorRange(editor, rangeStart, rangeEnd, "", rangeStart);
  state.vimMessage = enterInsert ? "changed" : "deleted";
  if (enterInsert) setVimMode("insert", editor, { recordHistory: false });
}

function copyVimRange(editor, start, end) {
  const rangeStart = Math.max(0, Math.min(start, end));
  const rangeEnd = Math.max(rangeStart, Math.max(start, end));
  state.vimRegister = editor.value.slice(rangeStart, rangeEnd);
  state.vimRegisterType = "char";
  state.vimMessage = "yanked";
}

function copyVimVisualSelection(editor) {
  const { start, end } = visualSelectionRange(editor);
  state.vimRegister = editor.value.slice(start, end);
  state.vimRegisterType = state.vimMode === "visual-line" ? "line" : "char";
  state.vimMessage = "visual yanked";
  state.vimMode = "normal";
  clearVimVisualState();
  moveEditorCursor(editor, start);
}

function deleteVimVisualSelection(editor, enterInsert = false) {
  const { start, end } = visualSelectionRange(editor);
  state.vimRegister = editor.value.slice(start, end);
  state.vimRegisterType = state.vimMode === "visual-line" ? "line" : "char";
  state.vimMode = "normal";
  clearVimVisualState();
  replaceEditorRange(editor, start, end, "", start);
  state.vimMessage = enterInsert ? "visual changed" : "visual deleted";
  if (enterInsert) setVimMode("insert", editor, { recordHistory: false });
}

function changeToLineEnd(editor) {
  const end = lineEndAt(editor.value, editor.selectionStart);
  deleteVimRange(editor, editor.selectionStart, end, true);
}

function deleteToLineEnd(editor) {
  const end = lineEndAt(editor.value, editor.selectionStart);
  deleteVimRange(editor, editor.selectionStart, end);
}

function joinVimLines(editor, count = 1) {
  let position = editor.selectionStart;
  for (let index = 0; index < count; index += 1) {
    const end = lineEndAt(editor.value, position);
    if (end >= editor.value.length) break;
    replaceEditorRange(editor, end, end + 1, " ", end + 1);
    position = end;
  }
  state.vimMessage = "joined";
}

function findVimSearch(editor, direction = state.vimSearchDirection, fromCurrent = false) {
  const query = state.vimSearchQuery;
  if (!query) return;
  const value = editor.value;
  const start = fromCurrent
    ? editor.selectionStart + (direction > 0 ? 1 : -1)
    : editor.selectionStart + direction;
  let found = -1;
  if (direction > 0) {
    found = value.indexOf(query, Math.max(0, start));
    if (found < 0) found = value.indexOf(query, 0);
  } else {
    found = value.lastIndexOf(query, Math.max(0, start));
    if (found < 0) found = value.lastIndexOf(query);
  }
  if (found >= 0) {
    moveEditorCursor(editor, found);
    state.vimMessage = `${query} 찾음`;
  } else {
    state.vimMessage = `${query} 없음`;
  }
  updateEditorSettingsUi();
}

function motionTarget(editor, key, count = 1, explicitLine = null) {
  const { value, selectionStart } = editor;
  if (key === "w") {
    let position = selectionStart;
    for (let index = 0; index < count; index += 1) position = nextWordPosition(value, position);
    return { start: selectionStart, end: position };
  }
  if (key === "b") {
    let position = selectionStart;
    for (let index = 0; index < count; index += 1) position = previousWordPosition(value, position);
    return { start: position, end: selectionStart };
  }
  if (key === "$" || key === "End") return { start: selectionStart, end: lineEndAt(value, selectionStart) };
  if (key === "0") return { start: lineStartAt(value, selectionStart), end: selectionStart };
  if (key === "^") {
    const { start, end } = currentLineBounds(value, selectionStart);
    return { start: firstTextColumn(value, start, end), end: selectionStart };
  }
  if (key === "j" || key === "ArrowDown") {
    return lineRangeWithBreakBounds(value, selectionStart, count + 1);
  }
  if (key === "k" || key === "ArrowUp") {
    const current = currentLineNumber(value, selectionStart);
    const targetStart = lineStartByNumber(value, Math.max(1, current - count));
    const currentEnd = lineWithBreakBounds(value, selectionStart).end;
    return { start: targetStart, end: currentEnd };
  }
  if (key === "G") {
    const targetLine = explicitLine || totalLineCount(value);
    const currentLine = currentLineNumber(value, selectionStart);
    const firstLine = Math.min(currentLine, targetLine);
    const lastLine = Math.max(currentLine, targetLine);
    return {
      start: lineStartByNumber(value, firstLine),
      end: lineRangeWithBreakBounds(value, lineStartByNumber(value, lastLine), 1).end,
    };
  }
  return null;
}

function hasUnsavedChanges() {
  return Boolean(state.selectedFile) && getEditorValue() !== state.lastSavedContent;
}

function updateDirtyState() {
  if (!state.selectedFile) return;
  const dirty = hasUnsavedChanges();
  setText("fileStatus", dirty ? "수정됨 · 저장하지 않음" : "저장됨");
  $("saveFileButton").classList.toggle("dirty", dirty);
  updateEditorStatus();
}

function handleEditorInput() {
  if (state.editorApplyingValue) return;
  if (
    !state.codeMirror
    && state.editorMode === "vim"
    && state.vimMode !== "insert"
    && $("fileEditor").value !== state.editorSnapshotBeforeIme
  ) {
    $("fileEditor").value = state.editorSnapshotBeforeIme;
  }
  updateEditorVisuals();
  updateDirtyState();
}

function handleEditorCompositionStart(event) {
  state.editorComposing = true;
  state.editorSnapshotBeforeIme = getEditorValue();
  if (state.editorMode === "vim" && state.vimMode !== "insert") {
    event.preventDefault();
  }
}

function handleEditorCompositionEnd() {
  if (state.editorMode === "vim" && state.vimMode !== "insert") {
    setEditorValue(state.editorSnapshotBeforeIme);
  }
  state.editorComposing = false;
}

function indentEditorSelection(editor) {
  const { value, selectionStart, selectionEnd } = editor;
  pushEditorHistory(editor);
  if (selectionStart !== selectionEnd && value.slice(selectionStart, selectionEnd).includes("\n")) {
    const lineStart = value.lastIndexOf("\n", selectionStart - 1) + 1;
    const selectedEnd =
      selectionEnd > selectionStart && value[selectionEnd - 1] === "\n"
        ? selectionEnd - 1
        : selectionEnd;
    const selected = value.slice(lineStart, selectedEnd);
    const indented = selected.replace(/^/gm, EDITOR_INDENT);
    editor.value = value.slice(0, lineStart) + indented + value.slice(selectedEnd);
    const diff = indented.length - selected.length;
    editor.selectionStart = selectionStart + EDITOR_INDENT.length;
    editor.selectionEnd = selectionEnd + diff;
    return;
  }
  editor.setRangeText(EDITOR_INDENT, selectionStart, selectionEnd, "end");
}

function outdentEditorSelection(editor) {
  const { value, selectionStart, selectionEnd } = editor;
  pushEditorHistory(editor);
  const lineStart = value.lastIndexOf("\n", selectionStart - 1) + 1;
  const selectedEnd =
    selectionEnd > selectionStart && value[selectionEnd - 1] === "\n"
      ? selectionEnd - 1
      : selectionEnd;
  const selected = value.slice(lineStart, selectedEnd);
  let removedBeforeStart = 0;
  let removedBeforeEnd = 0;
  let offset = lineStart;
  const outdented = selected
    .split("\n")
    .map((line) => {
      const removeCount = line.startsWith("\t")
        ? 1
        : Math.min(EDITOR_INDENT.length, line.match(/^ */)?.[0].length || 0);
      if (offset < selectionStart) removedBeforeStart += removeCount;
      if (offset < selectionEnd) removedBeforeEnd += removeCount;
      offset += line.length + 1;
      return line.slice(removeCount);
    })
    .join("\n");
  editor.value = value.slice(0, lineStart) + outdented + value.slice(selectedEnd);
  editor.selectionStart = Math.max(lineStart, selectionStart - removedBeforeStart);
  editor.selectionEnd = Math.max(editor.selectionStart, selectionEnd - removedBeforeEnd);
}

function vimCountValue(defaultValue = 1) {
  const count = state.vimCount ? Number(state.vimCount) : defaultValue;
  state.vimCount = "";
  return Number.isFinite(count) && count > 0 ? count : defaultValue;
}

function clearVimPending(message = "") {
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  if (message) state.vimMessage = message;
  updateEditorSettingsUi();
}

function applyVimOperator(editor, key) {
  const operator = state.vimPending;
  const explicitMotionCount = state.vimCount ? Number(state.vimCount) : null;
  const count = state.vimOperatorCount * vimCountValue(1);
  if ((operator === "d" || operator === "y" || operator === "c") && key === operator) {
    if (operator === "d") deleteVimLine(editor, count);
    if (operator === "y") copyVimLine(editor, count);
    if (operator === "c") deleteVimLine(editor, count, true);
    clearVimPending();
    return true;
  }
  const target = motionTarget(editor, key, count, explicitMotionCount);
  if (!target) {
    clearVimPending();
    return true;
  }
  if (operator === "d") deleteVimRange(editor, target.start, target.end);
  if (operator === "y") copyVimRange(editor, target.start, target.end);
  if (operator === "c") deleteVimRange(editor, target.start, target.end, true);
  clearVimPending();
  return true;
}

function handleVimVisualKey(editor, key) {
  if (state.vimPending === "g") {
    if (key === "g") {
      moveToLine(editor, state.vimOperatorCount);
      clearVimPending();
      return true;
    }
    clearVimPending();
    return true;
  }
  const count = () => vimCountValue(1);
  const { value } = editor;
  if (key === "v" && state.vimMode === "visual") {
    exitVimVisualMode(editor);
  } else if (key === "V" && state.vimMode === "visual-line") {
    exitVimVisualMode(editor);
  } else if (key === "V") {
    state.vimMode = "visual-line";
    updateVisualSelection(editor);
    updateEditorSettingsUi();
  } else if (key === "v") {
    state.vimMode = "visual";
    updateVisualSelection(editor);
    updateEditorSettingsUi();
  } else if (key === "o") {
    const anchor = state.vimVisualAnchor;
    state.vimVisualAnchor = state.vimVisualCursor;
    state.vimVisualCursor = anchor;
    updateVisualSelection(editor);
  } else if (key === "y") {
    copyVimVisualSelection(editor);
  } else if (key === "d" || key === "x" || key === "Delete") {
    deleteVimVisualSelection(editor);
  } else if (key === "c" || key === "s") {
    deleteVimVisualSelection(editor, true);
  } else if (key === "h" || key === "ArrowLeft") {
    moveEditorHorizontal(editor, -count());
  } else if (key === "l" || key === "ArrowRight") {
    moveEditorHorizontal(editor, count());
  } else if (key === "j" || key === "ArrowDown") {
    const amount = count();
    for (let index = 0; index < amount; index += 1) moveEditorVertical(editor, 1);
  } else if (key === "k" || key === "ArrowUp") {
    const amount = count();
    for (let index = 0; index < amount; index += 1) moveEditorVertical(editor, -1);
  } else if (key === "0" || key === "Home") {
    moveEditorCursor(editor, lineStartAt(value, state.vimVisualCursor ?? editor.selectionStart));
  } else if (key === "^") {
    const cursor = state.vimVisualCursor ?? editor.selectionStart;
    const { start, end } = currentLineBounds(value, cursor);
    moveEditorCursor(editor, firstTextColumn(value, start, end));
  } else if (key === "$" || key === "End") {
    moveEditorCursor(editor, normalCursorEndAt(value, state.vimVisualCursor ?? editor.selectionStart));
  } else if (key === "w") {
    moveToNextWord(editor, count());
  } else if (key === "e") {
    moveToWordEnd(editor, count());
  } else if (key === "b") {
    moveToPreviousWord(editor, count());
  } else if (key === "g") {
    state.vimPending = "g";
    state.vimOperatorCount = vimCountValue(1);
    updateEditorSettingsUi();
  } else if (key === "G") {
    moveToLine(editor, state.vimCount ? vimCountValue(1) : totalLineCount(value));
  } else {
    clearVimPending();
  }
  return true;
}

function handleVimKeydown(event) {
  if (state.editorMode !== "vim") return false;
  const editor = event.currentTarget;
  const key = event.key;
  if (event.isComposing || event.keyCode === 229) {
    if (state.vimMode !== "insert") {
      event.preventDefault();
      event.stopPropagation();
      return true;
    }
    return false;
  }
  if (key === "Escape" || (event.ctrlKey && key === "[")) {
    event.preventDefault();
    event.stopPropagation();
    if (state.vimMode === "insert") {
      setVimMode("normal", editor, { fromInsert: true });
    } else if (isVimVisualMode()) {
      exitVimVisualMode(editor);
    } else {
      clearVimPending();
    }
    return true;
  }
  if (state.vimMode === "insert") return false;
  if (event.ctrlKey && key.toLowerCase() === "r") {
    event.preventDefault();
    event.stopPropagation();
    redoEditorChange(editor);
    return true;
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return false;

  const { value, selectionStart } = editor;
  const prevent = () => {
    event.preventDefault();
    event.stopPropagation();
  };

  prevent();

  if (/^[1-9]$/.test(key) || (key === "0" && state.vimCount)) {
    state.vimCount += key;
    updateEditorSettingsUi();
    return true;
  }

  if (isVimVisualMode()) {
    return handleVimVisualKey(editor, key);
  }

  if (state.vimPending === "r") {
    replaceVimChar(editor, key);
    clearVimPending();
    return true;
  }
  if (["d", "y", "c"].includes(state.vimPending)) {
    return applyVimOperator(editor, key);
  }
  if (state.vimPending === "g") {
    if (key === "g") {
      moveToLine(editor, state.vimOperatorCount);
      clearVimPending();
      return true;
    }
    clearVimPending();
    return true;
  }

  const count = () => vimCountValue(1);

  if (key === "i") {
    setVimMode("insert", editor);
  } else if (key === "a") {
    moveEditorCursor(editor, Math.min(selectionStart + 1, lineEndAt(value, selectionStart)), null, {
      normal: false,
    });
    setVimMode("insert", editor);
  } else if (key === "I") {
    const { start, end } = currentLineBounds(value, selectionStart);
    moveEditorCursor(editor, firstTextColumn(value, start, end), null, { normal: false });
    setVimMode("insert", editor);
  } else if (key === "A") {
    moveEditorCursor(editor, lineEndAt(value, selectionStart), null, { normal: false });
    setVimMode("insert", editor);
  } else if (key === "o") {
    insertVimLine(editor, false);
  } else if (key === "O") {
    insertVimLine(editor, true);
  } else if (key === "v") {
    enterVimVisualMode(editor, "visual");
  } else if (key === "V") {
    enterVimVisualMode(editor, "visual-line");
  } else if (key === "h" || key === "ArrowLeft") {
    moveEditorHorizontal(editor, -count());
  } else if (key === "l" || key === "ArrowRight") {
    moveEditorHorizontal(editor, count());
  } else if (key === "j" || key === "ArrowDown") {
    const amount = count();
    for (let index = 0; index < amount; index += 1) moveEditorVertical(editor, 1);
  } else if (key === "k" || key === "ArrowUp") {
    const amount = count();
    for (let index = 0; index < amount; index += 1) moveEditorVertical(editor, -1);
  } else if (key === "0" || key === "Home") {
    moveEditorCursor(editor, lineStartAt(value, selectionStart));
  } else if (key === "^") {
    const { start, end } = currentLineBounds(value, selectionStart);
    moveEditorCursor(editor, firstTextColumn(value, start, end));
  } else if (key === "$" || key === "End") {
    moveEditorCursor(editor, normalCursorEndAt(value, selectionStart));
  } else if (key === "w") {
    moveToNextWord(editor, count());
  } else if (key === "e") {
    moveToWordEnd(editor, count());
  } else if (key === "b") {
    moveToPreviousWord(editor, count());
  } else if (key === "g") {
    state.vimPending = "g";
    state.vimOperatorCount = vimCountValue(1);
  } else if (key === "G") {
    moveToLine(editor, state.vimCount ? vimCountValue(1) : totalLineCount(value));
  } else if (key === "x" || key === "Delete") {
    const amount = count();
    for (let index = 0; index < amount; index += 1) deleteVimChar(editor);
  } else if (key === "d" || key === "y" || key === "c") {
    state.vimPending = key;
    state.vimOperatorCount = vimCountValue(1);
  } else if (key === "D") {
    deleteToLineEnd(editor);
  } else if (key === "C") {
    changeToLineEnd(editor);
  } else if (key === "r") {
    state.vimPending = "r";
  } else if (key === "s") {
    deleteVimChar(editor);
    setVimMode("insert", editor, { recordHistory: false });
  } else if (key === "p") {
    pasteVimRegister(editor, false, count());
  } else if (key === "P") {
    pasteVimRegister(editor, true, count());
  } else if (key === "J") {
    joinVimLines(editor, count());
  } else if (key === "u") {
    state.vimCount = "";
    undoEditorChange(editor);
  } else if (key === "/") {
    state.vimCount = "";
    openEditorCommandLine("search");
  } else if (key === ":") {
    state.vimCount = "";
    openEditorCommandLine("command");
  } else if (key === "n") {
    state.vimCount = "";
    findVimSearch(editor, state.vimSearchDirection || 1);
  } else if (key === "N") {
    state.vimCount = "";
    findVimSearch(editor, -(state.vimSearchDirection || 1));
  } else {
    clearVimPending();
    return true;
  }
  if (!["d", "g", "y", "c", "r"].includes(key)) clearVimPending();
  else updateEditorSettingsUi();
  return true;
}

function handleEditorKeydown(event) {
  const shortcut = event.metaKey || event.ctrlKey;
  if (shortcut && event.key.toLowerCase() === "s") {
    event.preventDefault();
    void withErrors(saveFile, "파일을 저장하는 중입니다.");
    return;
  }
  if (shortcut && event.key === "Enter") {
    const primary = currentPrimaryAction();
    if (primary) {
      event.preventDefault();
      void withErrors(() => runTabAction(primary.id), `${primary.label} 작업을 실행하는 중입니다.`);
    }
    return;
  }
  if (shortcut && event.key.toLowerCase() === "p") {
    const filter = optional("resourceFilterInput");
    if (filter && !filter.classList.contains("hidden")) {
      event.preventDefault();
      filter.focus();
      filter.select();
      return;
    }
  }
  if (handleVimKeydown(event)) return;
  if (event.key !== "Tab") return;
  event.preventDefault();
  const editor = event.currentTarget;
  if (event.shiftKey) {
    outdentEditorSelection(editor);
  } else {
    indentEditorSelection(editor);
  }
  updateEditorVisuals();
  updateDirtyState();
}

function handleEditorBeforeInput(event) {
  if (state.editorMode === "vim" && (state.vimMode === "normal" || isVimVisualMode())) {
    event.preventDefault();
  }
}

function confirmDiscardChanges() {
  if (!hasUnsavedChanges()) return true;
  return window.confirm("저장하지 않은 변경이 있습니다. 이동하면 변경 내용이 사라집니다. 계속할까요?");
}

function selectionKey(problemId = state.selectedProblem, tabId = state.selectedTab) {
  return `${problemId || "-"}:${tabId || "-"}`;
}

function persistedView() {
  const view = readStorage(PERSISTED_VIEW_KEY);
  return view && typeof view === "object" ? view : {};
}

function rememberView() {
  const previous = persistedView();
  writeStorage(PERSISTED_VIEW_KEY, {
    ...previous,
    problemId: state.selectedProblem || previous.problemId || null,
    tabId: state.selectedTab,
    filePath: state.selectedFile,
    tabSelections: state.tabSelections,
    problemFolderCollapsed: state.problemFolderCollapsed,
  });
}

function restoreViewPreference(problems) {
  const view = persistedView();
  if (view.problemFolderCollapsed && typeof view.problemFolderCollapsed === "object") {
    state.problemFolderCollapsed = Object.fromEntries(
      Object.entries(view.problemFolderCollapsed).filter(([, collapsed]) => collapsed === true)
    );
  }
  if (view.tabSelections && typeof view.tabSelections === "object") {
    state.tabSelections = { ...state.tabSelections, ...view.tabSelections };
  }
  if (view.problemId && view.tabId && view.filePath) {
    state.tabSelections[selectionKey(view.problemId, view.tabId)] = view.filePath;
  }
  const problemIds = new Set((problems || []).map((problem) => problem.problemId));
  const preferredProblem = problemIds.has(view.problemId) ? view.problemId : null;
  const preferredTab = TAB_CONFIGS[view.tabId] ? view.tabId : "info";
  return { problemId: preferredProblem, tabId: preferredTab };
}

function rememberSelectedFile() {
  if (!state.selectedProblem || !state.selectedTab || !state.selectedFile) return;
  state.tabSelections[selectionKey()] = state.selectedFile;
  rememberView();
}

function renderWorkspace(data) {
  state.workspace = data;
  setText("workspaceLabel", "문제 제작 워크스페이스");
  if (!state.selectedProblem) {
    updateMobileHeader("문제를 선택하세요", `${data.problemCount}개 문제`);
  }
  const folders = data.folders || [];
  const folderText = folders.length
    ? folders.map((folder) => `${folder.label} ${folder.problemCount}`).join(" · ")
    : "폴더 없음";
  $("workspaceStatus").innerHTML = `
    <div>문제 수: ${data.problemCount}</div>
    <div class="workspace-ok">폴더: ${escapeHtml(folderText)}</div>
  `;
}

function renderProblems(problems) {
  state.problems = problems;
  const list = $("problemList");
  list.innerHTML = "";
  if (!problems.length) {
    list.textContent = "등록된 문제가 없습니다.";
    list.classList.add("muted");
    return;
  }
  list.classList.remove("muted");
  const grouped = new Map();
  for (const problem of problems) {
    const folder = folderLabel(problem.folder);
    if (!grouped.has(folder)) grouped.set(folder, []);
    grouped.get(folder).push(problem);
  }
  for (const [folder, folderProblems] of grouped) {
    const collapsed = isProblemFolderCollapsed(folder);
    const section = document.createElement("section");
    section.className = "problem-folder-section";
    section.classList.toggle("collapsed", collapsed);
    const heading = document.createElement("div");
    heading.className = "problem-folder-row";
    heading.innerHTML = `
      <button
        class="problem-folder"
        type="button"
        aria-expanded="${collapsed ? "false" : "true"}"
        aria-label="${escapeHtml(folder)} 폴더 ${collapsed ? "펼치기" : "접기"}"
      >
        <span class="problem-folder-label">${escapeHtml(folder)}</span>
        <span class="problem-folder-count">${folderProblems.length}</span>
      </button>
    `;
    heading.querySelector(".problem-folder").addEventListener("click", () => {
      toggleProblemFolder(folder);
    });
    section.appendChild(heading);
    list.appendChild(section);
    if (collapsed) continue;
    for (const problem of folderProblems) {
      const item = document.createElement("button");
      item.className = "list-item";
      item.type = "button";
      item.innerHTML = `
        <strong>${escapeHtml(problemLabel(problem))}</strong>
        <span>${escapeHtml(problem.defaultProfile || "hidden")} · v${escapeHtml(problem.version || "-")}</span>
      `;
      item.classList.toggle("active", problem.problemId === state.selectedProblem);
      if (problem.problemId === state.selectedProblem) item.setAttribute("aria-current", "page");
      item.addEventListener("click", () => {
        void withErrors(() => selectProblem(problem.problemId), "문제를 불러오는 중입니다.");
        closeSidebar();
      });
      section.appendChild(item);
    }
  }
}

function filesForTab(tabId = state.selectedTab) {
  if (!state.detail) return [];
  if (tabId === "solutions") {
    return state.files.filter((file) => file.path.startsWith("solutions/"));
  }
  const paths = TAB_CONFIGS[tabId].files || [];
  return paths
    .map((path) => state.files.find((file) => file.path === path) || { path, size: 0 })
    .filter(Boolean);
}

function renderTabButtons() {
  for (const button of document.querySelectorAll(".tab-button")) {
    const active = button.dataset.tab === state.selectedTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    if (active) button.scrollIntoView({ block: "nearest", inline: "center" });
  }
}

function renderTabActions() {
  const actions = $("tabActions");
  actions.innerHTML = "";
  for (const action of TAB_CONFIGS[state.selectedTab].actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    if (action.id === "runAllChecks") button.id = "runAllButton";
    if (action.id === "buildPack") button.id = "packButton";
    if (action.id === "buildAllPacks") button.id = "buildAllPacksButton";
    if (action.primary) button.className = "primary";
    if (action.danger) button.className = "danger";
    button.addEventListener("click", () => {
      if (action.id === "uploadSolutions") {
        try {
          openSolutionUpload();
        } catch (error) {
          showAlert(error.message, "error", { title: "솔루션 업로드 실패", timeout: 9000 });
        }
        return;
      }
      void withErrors(() => runTabAction(action.id), `${action.label} 작업을 실행하는 중입니다.`);
    });
    actions.appendChild(button);
  }
  updateGlobalActionState();
}

function updateEditorPanelMode() {
  const infoMode = state.selectedTab === "info";
  const buildMode = state.selectedTab === "build";
  const solutionsMode = state.selectedTab === "solutions";
  const layout = document.querySelector(".studio-layout");
  layout?.classList.toggle("info-mode", infoMode);
  layout?.classList.toggle("solutions-mode", solutionsMode);
  const editorPanel = document.querySelector(".editor-panel");
  editorPanel?.classList.toggle("build-mode", buildMode);
  editorPanel?.classList.toggle("solutions-hidden", solutionsMode);
  optional("buildDashboard")?.classList.toggle("hidden", !buildMode);
}

function updateDownloadLink(link, pack, fallbackLabel = "다운로드") {
  if (!link) return;
  link.classList.toggle("hidden", !pack?.downloadUrl);
  if (pack?.downloadUrl) {
    link.href = pack.downloadUrl;
    link.textContent = `${pack.archiveLabel || fallbackLabel} 다운로드`;
  }
}

function updateBuildDashboard() {
  const dashboard = optional("buildDashboard");
  if (!dashboard || state.selectedTab !== "build") return;
  const result = currentProblemResult();
  const fullTest = result?.fullTest || state.lastFullTest;
  const pack = state.lastPackResult || result?.lastPackResult;
  const profile = optional("packVerifyProfileInput")?.value.trim() || "hidden";
  let tone = "neutral";
  let title = "전체 테스트 필요";
  let summary = "팩 빌드 전에 현재 문제의 전체 테스트를 실행해야 합니다.";
  let testState = "대기";
  let testDetail = "아직 통과 기록이 없습니다.";

  if (state.activePackJob) {
    tone = "running";
    title = "팩 빌드 진행 중";
    summary = packJobSummary(state.activePackJob);
    testState = "빌드 중";
    testDetail = "완료되면 최근 팩과 다운로드 링크가 갱신됩니다.";
  } else if (hasFreshFullTest()) {
    tone = "success";
    title = "전체 테스트 통과";
    summary = fullTest?.summary || "현재 문제 팩을 빌드할 수 있습니다.";
    testState = "통과";
    testDetail = fullTest?.checkedAt ? `${formatTime(fullTest.checkedAt)} 확인` : "검증 완료";
  } else if (result?.dirtyAfterFullTest) {
    tone = "stale";
    title = "재검증 필요";
    summary = result.dirtyReason || "변경사항이 있어 전체 테스트를 다시 실행해야 합니다.";
    testState = "변경됨";
    testDetail = fullTest?.summary || "최근 검증 이후 데이터가 바뀌었습니다.";
  } else if (fullTest && !fullTest.passed) {
    tone = "error";
    title = "전체 테스트 실패";
    summary = fullTest.summary || "실패한 단계를 확인한 뒤 다시 실행하세요.";
    testState = "실패";
    testDetail = fullTest.checkedAt ? `${formatTime(fullTest.checkedAt)} 실패` : "검증 실패";
  }

  const hero = optional("buildDashboardHero");
  if (hero) hero.className = `build-dashboard-hero ${tone}`;
  setText("buildDashboardTitle", title);
  setText("buildDashboardSummary", summary || "-");
  setText("buildDashboardTestState", testState);
  setText("buildDashboardTestDetail", testDetail || "-");
  setText("buildDashboardOutput", PACK_OUTPUT_DIR);
  setText("buildDashboardProfile", profile);
  setText(
    "buildDashboardPack",
    state.activePackJob ? packJobSummary(state.activePackJob) : pack?.archiveLabel || "아직 없음"
  );
  updateDownloadLink(optional("buildDashboardDownloadLink"), pack, "팩 파일");
}

function updateBuildPanel() {
  const panel = optional("buildPanel");
  if (!panel) return;
  const visible = state.selectedTab === "build";
  panel.classList.toggle("hidden", !visible);
  if (!visible) {
    updateEditorPanelMode();
    return;
  }

  const result = currentProblemResult();
  const status = optional("buildValidationStatus");
  const output = optional("packOutputLabel");
  const link = optional("packDownloadLink");
  if (output) output.textContent = PACK_OUTPUT_DIR;
  if (status) {
    if (state.activePackJob) {
      status.textContent = `팩 빌드 진행 중입니다. ${packJobSummary(state.activePackJob)}`;
    } else if (hasFreshFullTest()) {
      status.textContent = `전체 테스트 통과 상태입니다. 바로 현재 문제 팩을 빌드할 수 있습니다.`;
    } else if (result?.dirtyAfterFullTest) {
      status.textContent = result.dirtyReason || "변경사항이 있어 전체 테스트를 다시 실행해야 합니다.";
    } else {
      status.textContent = "팩 빌드 전 현재 문제의 전체 테스트를 먼저 통과해야 합니다.";
    }
  }
  if (link) {
    const pack = state.lastPackResult || result?.lastPackResult;
    updateDownloadLink(link, pack, "팩 파일");
  }
  updateEditorPanelMode();
  updateBuildDashboard();
}

async function runTabAction(actionId) {
  if (SAVE_BEFORE_ACTIONS.has(actionId)) await saveOpenFileIfDirty();
  return ACTIONS[actionId]();
}

function currentPrimaryAction() {
  return TAB_CONFIGS[state.selectedTab]?.actions?.find((action) => action.primary) || null;
}

function solutionExpectedStatusFromPath(path) {
  const parts = solutionParts(path);
  return EXPECTED_STATUS_BY_TOKEN[parts.expected] || "unknown";
}

function isReferenceSolutionPath(path) {
  return Boolean(path && path === state.detail?.metadata?.tools?.solution);
}

function solutionRowFacts(file) {
  const check = solutionCheckForPath(file.path);
  const metrics = solutionCheckMetrics(check);
  const expectedStatus = check?.expectedStatus || solutionExpectedStatusFromPath(file.path);
  const actualStatus = check?.actualStatus || "";
  const dirty = dirtySolutionSet().has(normalizedSolutionPath(file.path));
  const status = solutionValidationStatusForFile(file.path);
  return {
    check,
    metrics,
    dirty,
    status,
    expected: statusLabelForResult(expectedStatus),
    actual: dirty ? "재검증" : actualStatus ? statusLabelForResult(actualStatus) : "대기",
    runId: check?.runId || "-",
    message: normalizeErrorDetail(check?.message) || "",
  };
}

function renderSolutionResourceItem(list, file) {
  const facts = solutionRowFacts(file);
  const hasCases = facts.check && facts.metrics.totalCases;
  const item = document.createElement("div");
  item.className = `resource-item solution-row ${facts.status?.className || ""}`.trim();
  item.title = facts.status?.title || `${file.path} · ${roleForFile(file.path)}`;
  item.dataset.solutionPath = file.path;
  const active = file.path === state.selectedFile;
  item.classList.toggle("active", active);
  item.innerHTML = `
    <button class="solution-row-main" type="button" aria-pressed="${active ? "true" : "false"}">
      <span class="resource-main">
        <span class="resource-path">${escapeHtml(file.path)}</span>
        <span class="resource-role">${escapeHtml(roleForFile(file.path))}</span>
      </span>
      <span class="solution-result-grid">
        <span><small>기대</small><strong>${escapeHtml(facts.expected)}</strong></span>
        <span><small>실제</small><strong>${escapeHtml(facts.actual)}</strong></span>
        <span><small>케이스</small><strong>${
          hasCases ? `${escapeHtml(facts.metrics.okCases)}/${escapeHtml(facts.metrics.totalCases)}` : "-"
        }</strong></span>
      </span>
      <span class="resource-status">${escapeHtml(facts.status?.label || "대기")}</span>
    </button>
    ${
      facts.check
        ? `<div class="solution-metric-strip">
            <span><small>최대 시간</small><strong>${escapeHtml(formatDurationMs(facts.metrics.maxTimeMs))}</strong></span>
            <span><small>최대 메모리</small><strong>${escapeHtml(formatMemoryBytes(facts.metrics.maxMemoryBytes))}</strong></span>
            <span><small>run</small><strong>${escapeHtml(facts.runId)}</strong></span>
          </div>`
        : ""
    }
    <div class="solution-row-actions">
      <button type="button" data-solution-test="${escapeHtml(file.path)}">개별 테스트</button>
      <button
        type="button"
        data-solution-cases="${escapeHtml(file.path)}"
        ${facts.check ? "" : "disabled"}
        title="${facts.check ? "케이스별 채점 결과 보기" : "테스트 후 결과를 볼 수 있습니다."}"
      >채점 결과</button>
      <button type="button" data-solution-edit="${escapeHtml(file.path)}">소스 편집</button>
    </div>
    ${
      facts.check && (facts.message || facts.runId !== "-")
        ? `<div class="solution-row-detail">
            ${facts.message ? `<span title="${escapeHtml(facts.message)}">${escapeHtml(facts.message)}</span>` : ""}
          </div>`
        : ""
    }
  `;
  item.querySelector(".solution-row-main")?.addEventListener("click", () => {
    selectSolutionPath(file.path);
  });
  item.querySelector("[data-solution-test]")?.addEventListener("click", (event) => {
    event.stopPropagation();
    void withErrors(() => verifySingleSolution(file.path), "솔루션 하나를 테스트하는 중입니다.");
  });
  item.querySelector("[data-solution-cases]")?.addEventListener("click", (event) => {
    event.stopPropagation();
    void withErrors(() => openSolutionCasesModal(file.path), "채점 결과를 여는 중입니다.");
  });
  item.querySelector("[data-solution-edit]")?.addEventListener("click", (event) => {
    event.stopPropagation();
    void withErrors(() => openSolutionEditModal(file.path), "솔루션 편집창을 여는 중입니다.");
  });
  list.appendChild(item);
}

function renderTabFiles() {
  const list = $("tabFiles");
  const files = filesForTab();
  const filterInput = optional("resourceFilterInput");
  const summary = optional("resourceSummary");
  const filter = state.resourceFilters[state.selectedTab] || "";
  list.classList.toggle("solution-resource-list", state.selectedTab === "solutions");
  if (filterInput) {
    filterInput.value = filter;
    filterInput.classList.toggle("hidden", !files.length);
  }
  list.innerHTML = "";
  if (!files.length) {
    list.textContent =
      state.selectedTab === "solutions" ? "업로드된 솔루션이 없습니다." : "작업 대상이 없습니다.";
    list.classList.add("muted");
    if (summary) summary.textContent = list.textContent;
    return;
  }
  const visibleFiles = files.filter((file) => {
    const text = `${file.path} ${roleForFile(file.path)}`.toLowerCase();
    return !filter || text.includes(filter.toLowerCase());
  });
  const matchCount = visibleFiles.filter((file) => validationStatusForFile(file.path)?.className === "match").length;
  const mismatchCount = visibleFiles.filter((file) => validationStatusForFile(file.path)?.className === "mismatch").length;
  const staleCount = visibleFiles.filter((file) => validationStatusForFile(file.path)?.className === "stale").length;
  if (summary) {
    const statusParts = [
      `${visibleFiles.length}/${files.length}개 표시`,
      matchCount ? `통과 ${matchCount}` : "",
      mismatchCount ? `실패 ${mismatchCount}` : "",
      staleCount ? `재검증 ${staleCount}` : "",
    ].filter(Boolean);
    summary.textContent = statusParts.join(" · ");
  }
  if (!visibleFiles.length) {
    list.textContent = "필터와 일치하는 작업 대상이 없습니다.";
    list.classList.add("muted");
    return;
  }
  list.classList.remove("muted");
  let previousGroup = "";
  for (const file of visibleFiles) {
    const group = tabResourceGroup(file.path);
    if (group !== previousGroup) {
      const heading = document.createElement("div");
      heading.className = "resource-group";
      heading.textContent = group;
      list.appendChild(heading);
      previousGroup = group;
    }
    if (state.selectedTab === "solutions") {
      renderSolutionResourceItem(list, file);
      continue;
    }
    const item = document.createElement("button");
    const validationStatus = validationStatusForFile(file.path);
    item.className = "resource-item";
    if (state.selectedTab === "solutions") item.classList.add("solution-row");
    item.type = "button";
    if (validationStatus) item.classList.add(validationStatus.className);
    item.title = validationStatus?.title || `${file.path} · ${roleForFile(file.path)}`;
    item.innerHTML = `
      <span class="resource-main">
        <span class="resource-path">${escapeHtml(file.path)}</span>
        <span class="resource-role">${escapeHtml(roleForFile(file.path))}</span>
      </span>
      <span class="resource-status">${escapeHtml(validationStatus?.label || "대기")}</span>
    `;
    const active = file.path === state.selectedFile;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", active ? "true" : "false");
    item.addEventListener("click", () => {
      void withErrors(() => openFile(file.path), "파일을 불러오는 중입니다.");
    });
    list.appendChild(item);
  }
}

function renderSolutionValidationSummary() {
  const panel = optional("solutionValidationSummary");
  if (!panel) return;
  panel.className = "solution-validation-summary hidden";
  panel.innerHTML = "";
}

function populateMetadataForm(metadata) {
  const limits = metadata?.limits || {};
  const tools = metadata?.tools || {};
  setText("metadataProblemId", state.selectedProblem || metadata?.problemId || "-");
  $("metadataProblemIdInput").value = state.selectedProblem || metadata?.problemId || "";
  $("metadataTitle").value = metadata?.title || "";
  $("metadataFolder").value = metadata?.folder || "";
  $("metadataVersion").value = metadata?.version ?? 1;
  $("metadataDefaultProfile").value = metadata?.defaultProfile || "hidden";
  $("metadataCompileTimeout").value = limits.compileTimeoutMs ?? 5000;
  $("metadataGenerationTimeout").value = limits.generationTimeoutMs ?? 5000;
  $("metadataSolutionTimeout").value = limits.solutionTimeoutMs ?? 2000;
  $("metadataUserTimeout").value = limits.userTimeoutMs ?? 2000;
  $("metadataToolGenerator").value = tools.generator || "generator/generator.cpp";
  $("metadataToolGeneratorConfig").value = tools.generatorConfig || "generator/cases.yml";
  $("metadataToolValidator").value = tools.validator || "validator/validator.cpp";
  $("metadataToolChecker").value = tools.checker || "checker/judge.cpp";
  $("metadataToolSolution").value = tools.solution || "solutions/main_solution.ac.cpp";
  renderMetadataValidation();
}

function solutionParts(path) {
  const filename = (path || "").split("/").pop() || "";
  const match = filename.match(/^(.*)\.(ac|wa|tle|mle)(\.[^.]+)$/);
  const extension = match ? match[3] : filename.match(/\.[^.]+$/)?.[0] || ".cpp";
  return {
    name: match ? match[1] : filename.replace(/\.[^.]+$/, ""),
    expected: match ? match[2] : "wa",
    language: LANGUAGE_BY_EXTENSION[extension.toLowerCase()] || "cpp",
  };
}

function roleForFile(path) {
  if (FILE_ROLES[path]) return FILE_ROLES[path];
  if (path?.startsWith("solutions/")) {
    const parts = solutionParts(path);
    if (parts.expected === "ac") return "정답 솔루션";
    return `${parts.expected.toUpperCase()} 예상 솔루션`;
  }
  if (path?.endsWith(".md")) return "메모";
  return "작업 파일";
}

function tabResourceGroup(path) {
  if (path === "problem.json") return "Metadata";
  if (path?.startsWith("generator/")) return "Generator";
  if (path?.startsWith("validator/")) return "Validator";
  if (path?.startsWith("checker/")) return "Checker";
  if (path?.startsWith("solutions/")) return "Solutions";
  return "Files";
}

function formatSolutionFilename(name, expected, language) {
  const normalizedName = name.trim().replaceAll(" ", "_") || "solution";
  return `${normalizedName}.${expected}${EXTENSIONS[language] || ".cpp"}`;
}

function solutionNameError(value) {
  const name = value.trim().replaceAll(" ", "_");
  if (!name) return "솔루션 이름을 입력하세요.";
  if (!SAFE_SOLUTION_NAME.test(name)) return "영문, 숫자, _, -, . 만 사용할 수 있습니다.";
  return "";
}

function updateSolutionFormValidity(config) {
  const name = $(config.nameId).value;
  const error = solutionNameError(name);
  const expected = $(config.expectedId).value;
  const language = $(config.languageId).value;
  setText(config.previewId, formatSolutionFilename(name, expected, language));
  setText(config.errorId, error);
  $(config.buttonId).disabled = Boolean(error);
  $(config.previewId).classList.toggle("invalid", Boolean(error));
  return !error;
}

function updateSolutionPreview() {
  const valid = updateSolutionFormValidity({
    nameId: "solutionCreateName",
    expectedId: "solutionCreateExpected",
    languageId: "solutionCreateLanguage",
    previewId: "solutionCreatePreview",
    errorId: "solutionCreateNameError",
    buttonId: "solutionCreateButton",
  });
  updateModalEditorOptions();
  return valid;
}

function updateSolutionRenamePreview() {
  const valid = updateSolutionFormValidity({
    nameId: "solutionName",
    expectedId: "solutionExpected",
    languageId: "solutionLanguage",
    previewId: "solutionRenamePreview",
    errorId: "solutionNameError",
    buttonId: "solutionRenameButton",
  });
  updateModalEditorOptions();
  return valid;
}

function renderSolutionMetaForm() {
  updateSolutionRenamePreview();
}

function renderTaskPanel() {
  const config = TAB_CONFIGS[state.selectedTab];
  renderTabButtons();
  setText("taskTitle", config.title);
  setText("taskDescription", config.description);
  $("metadataForm").classList.toggle("hidden", state.selectedTab !== "info");
  renderSolutionMetaForm();
  updateBuildPanel();
  renderLastRunPanel();
  if (state.selectedTab === "info" && state.detail) {
    populateMetadataForm(state.detail.metadata);
  }
  renderTabActions();
  renderSolutionValidationSummary();
  renderTabFiles();
}

function clearEditor(message = "작업 대상을 선택하세요.") {
  state.selectedFile = null;
  setEditorValue("", { clearHistory: true });
  state.lastSavedContent = "";
  resetEditorHistory();
  resetVimTransientState();
  setText("fileTitle", "파일 없음");
  setText("fileStatus", message);
  $("fileEditor").setAttribute("aria-label", "파일 편집기");
  updateEditorVisuals();
  renderSolutionMetaForm();
  renderSolutionValidationSummary();
}

function selectSolutionPath(path) {
  if (!path) return;
  state.selectedFile = path;
  state.tabSelections[selectionKey()] = path;
  rememberView();
  renderTabFiles();
  renderSolutionValidationSummary();
}

async function refresh() {
  const seq = nextViewSeq();
  const workspace = await api("/api/workspace");
  if (!isCurrentView(seq)) return;
  const preferred = restoreViewPreference(workspace.problems || []);
  renderWorkspace(workspace);
  renderProblems(workspace.problems || []);
  const selectedStillExists = workspace.problems?.some(
    (problem) => problem.problemId === state.selectedProblem
  );
  if (selectedStillExists) {
    await selectProblem(state.selectedProblem, seq);
  } else if (preferred.problemId) {
    state.selectedTab = preferred.tabId;
    await selectProblem(preferred.problemId, seq);
  } else if (workspace.problems?.length) {
    await selectProblem(workspace.problems[0].problemId, seq);
  } else {
    state.selectedProblem = null;
    state.detail = null;
    state.files = [];
    state.lastSolutionVerification = null;
    state.lastRun = null;
    hideLastRunPanel();
    renderTaskPanel();
    clearEditor();
  }
}

async function selectProblem(problemId, seq = nextViewSeq()) {
  const switchedProblem = state.selectedProblem !== problemId;
  if (switchedProblem && !confirmDiscardChanges()) return;
  rememberSelectedFile();
  state.selectedProblem = problemId;
  const detail = await api(`/api/problems/${encodeURIComponent(problemId)}`);
  if (!isCurrentView(seq)) return;
  state.detail = detail;
  state.files = detail.files || [];
  if (switchedProblem) {
    state.selectedFile = null;
    setEditorValue("", { clearHistory: true });
    state.lastSavedContent = "";
    resetEditorHistory();
    resetVimTransientState();
    updateEditorVisuals();
  }
  restoreProblemLastResult(problemId);
  applyProblemMetadataToUi(detail.metadata);
  populateMetadataForm(detail.metadata);
  rememberView();
  await selectTab(state.selectedTab, seq);
}

async function selectTab(tabId, seq = nextViewSeq()) {
  if (tabId !== state.selectedTab && !confirmDiscardChanges()) return;
  rememberSelectedFile();
  state.selectedTab = tabId;
  rememberView();
  renderTaskPanel();
  resetWorkspaceScroll();
  const files = filesForTab(tabId);
  const rememberedPath = state.tabSelections[selectionKey(state.selectedProblem, tabId)];
  const remembered = files.find((file) => file.path === rememberedPath);
  const currentStillVisible = files.some((file) => file.path === state.selectedFile);
  if (tabId === "solutions") {
    const selected = remembered || (currentStillVisible ? files.find((file) => file.path === state.selectedFile) : null) || files[0];
    clearEditor("솔루션 소스 편집은 각 솔루션의 소스 편집 버튼에서 진행합니다.");
    if (selected) selectSolutionPath(selected.path);
    else renderTabFiles();
    return;
  }
  if (files.length && remembered) {
    await openFile(remembered.path, false, seq, true);
  } else if (files.length && !currentStillVisible) {
    await openFile(files[0].path, false, seq, true);
  } else if (!files.length) {
    clearEditor("이 탭에서 작업할 파일이 없습니다.");
  } else {
    renderTabFiles();
  }
}

async function refreshProblemFiles(seq = state.viewSeq) {
  if (!state.selectedProblem) return;
  const data = await api(`/api/problems/${encodeURIComponent(state.selectedProblem)}/files`);
  if (!isCurrentView(seq)) return;
  state.files = data.files || [];
  renderTabFiles();
}

async function openFile(path, refreshFiles = true, seq = nextViewSeq(), skipConfirm = false) {
  if (!state.selectedProblem) return;
  if (path !== state.selectedFile && !skipConfirm && !confirmDiscardChanges()) return;
  rememberSelectedFile();
  setText("fileTitle", path);
  setText("fileStatus", "불러오는 중...");
  const data = await api(
    `/api/problems/${encodeURIComponent(state.selectedProblem)}/files/${apiFilePath(path)}`
  );
  if (!isCurrentView(seq)) return;
  state.selectedFile = path;
  setEditorValue(data.content, { clearHistory: true });
  state.lastSavedContent = data.content;
  resetEditorHistory();
  resetVimTransientState();
  state.tabSelections[selectionKey()] = path;
  rememberView();
  setText("fileTitle", path);
  setText("fileStatus", "저장됨");
  $("fileEditor").setAttribute("aria-label", `${path} 파일 편집기`);
  updateEditorVisuals();
  updateDirtyState();
  if (refreshFiles) await refreshProblemFiles(seq);
  renderTabFiles();
  renderSolutionMetaForm();
  renderSolutionValidationSummary();
}

async function saveFile(options = {}) {
  if (!state.selectedProblem || !state.selectedFile) throw new Error("Open a file first.");
  const savedSolutionFile = state.selectedFile.startsWith("solutions/");
  const content = getEditorValue();
  await api(
    `/api/problems/${encodeURIComponent(state.selectedProblem)}/files/${apiFilePath(state.selectedFile)}`,
    {
      method: "PUT",
      body: JSON.stringify({ content }),
    }
  );
  state.lastSavedContent = content;
  setText("fileStatus", "저장됨");
  updateDirtyState();
  if (savedSolutionFile) {
    if (isReferenceSolutionPath(state.selectedFile)) {
      markAllSolutionsDirty("기준 정답 변경으로 모든 솔루션 재검증이 필요합니다.");
    } else {
      markSolutionDirty(state.selectedFile, `${state.selectedFile} 저장으로 솔루션 재검증이 필요합니다.`);
    }
  } else {
    if (
      state.selectedFile.startsWith("generator/")
      || state.selectedFile.startsWith("validator/")
      || state.selectedFile.startsWith("checker/")
    ) {
      setDirtySolutionPaths(solutionFilePaths());
    }
    markFullTestDirty(`${state.selectedFile} 저장으로 전체 테스트가 다시 필요합니다.`);
  }
  if (!options.silent) {
    showResult(`${state.selectedFile} 저장 완료`, "summary success");
  }
}

async function saveOpenFileIfDirty() {
  if (!hasUnsavedChanges()) return false;
  await saveFile({ silent: true });
  showResult("변경사항을 저장한 뒤 실행합니다.", "summary success");
  return true;
}

async function saveMetadata() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  if (metadataRawEditorDirty()) {
    throw new Error("원본 problem.json 편집 내용이 저장되지 않았습니다. 원본을 저장하거나 되돌린 뒤 폼을 저장하세요.");
  }
  const issues = metadataFormIssues();
  if (issues.length) {
    renderMetadataValidation();
    throw new Error(`문제 정보 저장 전에 확인하세요.\n${issues.join("\n")}`);
  }
  const metadata = currentMetadataDraft();
  const previousProblemId = state.selectedProblem;
  const nextProblemId = currentProblemIdDraft();
  if (nextProblemId !== previousProblemId) {
    const renameResult = await api(`/api/problems/${encodeURIComponent(previousProblemId)}/id`, {
      method: "PATCH",
      body: JSON.stringify({ problem_id: nextProblemId }),
    });
    applyProblemRenameResult(renameResult, previousProblemId);
  }
  const result = await api(`/api/problems/${encodeURIComponent(state.selectedProblem)}/metadata`, {
    method: "PATCH",
    body: JSON.stringify({ metadata }),
  });
  applyProblemMetadataToUi(result, { markDirty: true });
  showResult(
    nextProblemId !== previousProblemId
      ? `${previousProblemId} 문제 번호를 ${nextProblemId}로 변경했습니다.`
      : "문제 정보가 저장되었습니다.",
    "summary success"
  );
  if (state.selectedFile === "problem.json") await openFile("problem.json", true);
}

async function createProblem() {
  const problemId = $("newProblemId").value.trim();
  const title = $("newProblemTitle").value.trim() || "Untitled Problem";
  const folder = $("newProblemFolder").value.trim();
  const version = positiveIntegerInput("newProblemVersion", 1);
  const defaultProfile = textInputValue("newProblemDefaultProfile", "hidden");
  const limits = {
    compileTimeoutMs: positiveIntegerInput("newProblemCompileTimeout", 5000),
    generationTimeoutMs: positiveIntegerInput("newProblemGenerationTimeout", 5000),
    solutionTimeoutMs: positiveIntegerInput("newProblemSolutionTimeout", 2000),
    userTimeoutMs: positiveIntegerInput("newProblemUserTimeout", 2000),
  };
  await api("/api/problems", {
    method: "POST",
    body: JSON.stringify({
      problem_id: problemId,
      title,
      folder,
      version,
      default_profile: defaultProfile,
      limits,
    }),
  });
  closeModals();
  await refresh();
  await selectProblem(problemId);
  showResult(`Created problem ${problemId}`, "summary success");
}

function updateDeleteProblemButton() {
  const input = optional("deleteProblemConfirmInput");
  const button = optional("deleteProblemButton");
  if (!button) return;
  button.disabled = (
    !state.selectedProblem
    || input?.value !== DELETE_CONFIRM_PHRASE
    || document.body.getAttribute("aria-busy") === "true"
  );
}

function openDeleteProblemModal() {
  if (!state.selectedProblem) throw new Error("삭제할 문제를 먼저 선택하세요.");
  const problem = state.problems.find((item) => item.problemId === state.selectedProblem);
  const label = problem ? problemLabel(problem) : state.selectedProblem;
  setText("deleteProblemDescription", `${label} 문제를 삭제합니다.`);
  $("deleteProblemConfirmInput").value = "";
  updateDeleteProblemButton();
  openModal("deleteProblemModal");
}

async function deleteSelectedProblem() {
  if (!state.selectedProblem) throw new Error("삭제할 문제를 먼저 선택하세요.");
  const problemId = state.selectedProblem;
  const confirmPhrase = $("deleteProblemConfirmInput").value;
  if (confirmPhrase !== DELETE_CONFIRM_PHRASE) {
    throw new Error(`삭제하려면 "${DELETE_CONFIRM_PHRASE}"를 정확히 입력하세요.`);
  }
  await api(`/api/problems/${encodeURIComponent(problemId)}`, {
    method: "DELETE",
    body: JSON.stringify({ confirm_phrase: confirmPhrase }),
  });
  clearProblemLastResult(problemId);
  if (state.activePackJob?.problemId === problemId) clearPackJob();
  state.selectedProblem = null;
  state.selectedFile = null;
  state.detail = null;
  state.files = [];
  closeModals();
  await refresh();
  showAlert(`${problemId} 문제를 삭제했습니다.`, "success", {
    title: "문제 삭제 완료",
    timeout: 5000,
  });
}

function showCasesAlertDetails(result) {
  if (result.valid) return;
  const detail = (result.diagnostics || [])
    .map((item) => {
      const location = [item.profile, item.location, item.line].filter(Boolean).join(" / ");
      return location ? `${location}: ${item.message}` : item.message;
    })
    .join("; ");
  showAlert(`cases.yml 검사 실패: ${detail || "확인할 항목이 있습니다."}`, "error", {
    timeout: 10000,
  });
}

function formatCasesDiagnostics(result) {
  const diagnostics = result.diagnostics || [];
  if (!diagnostics.length) return "cases.yml을 확인하세요.";
  return diagnostics
    .map((item) => {
      const location = [
        item.path || "generator/cases.yml",
        item.line ? `line ${item.line}` : "",
        item.profile ? `profile ${item.profile}` : "",
        item.location ? `location ${item.location}` : "",
      ].filter(Boolean).join(" · ");
      return [
        location,
        item.message ? `message: ${item.message}` : "",
        item.hint ? `hint: ${item.hint}` : "",
      ].filter(Boolean).join("\n");
    })
    .join("\n\n");
}

async function compileCases(options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  if (options.clear !== false) clearOutput();
  const result = await api(`/api/problems/${state.selectedProblem}/cases/compile`, {
    method: "POST",
    body: JSON.stringify({ profile: null }),
  });
  appendOutput(JSON.stringify(result, null, 2));
  showCasesAlertDetails(result);
  showLastRun(
    result.valid ? "Cases 검사 완료" : "Cases 검사 실패",
    result.valid
      ? `${result.profiles?.length || 0}개 profile을 확인했습니다.`
      : formatOperationFailure(
        `cases.yml compile failed\n\n${formatCasesDiagnostics(result)}`,
        ["대상: generator/cases.yml"]
      ),
    result.valid ? "success" : "error"
  );
  showResult(
    result.valid ? "cases.yml OK" : "cases.yml에 문제가 있습니다.",
    result.valid ? "summary success" : "summary error"
  );
  return result;
}

async function compileTool(tool, label, options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  if (options.clear !== false) clearOutput();
  const ownsProgress = !state.progress.active;
  if (ownsProgress) {
    beginProgress(`${label} 컴파일`, [{ label: `${label} 컴파일`, status: "running" }]);
    setProgressInsight(`${label} 컴파일`, `${label} 소스코드를 컴파일하고 있습니다.`);
  }
  try {
    const result = await api(`/api/problems/${state.selectedProblem}/tools/compile`, {
      method: "POST",
      body: JSON.stringify({ tool }),
    });
    appendOutput(JSON.stringify(result.labels || {}, null, 2));
    if (ownsProgress) setProgressStep(0, "success", `${label} 컴파일 완료`);
    showLastRun(`${label} 컴파일 완료`, `${label} 도구를 사용할 준비가 되었습니다.`, "success");
    showResult(`${label} compiled.`, "summary success");
    return result;
  } catch (error) {
    const detail = normalizeErrorDetail(error.message);
    if (ownsProgress) setProgressStep(0, "error", detail);
    showLastRun(
      `${label} 컴파일 실패`,
      formatOperationFailure(detail, [
        `대상: ${tool}`,
        state.lastStreamDetail ? `마지막 단계: ${state.lastStreamDetail}` : "",
      ]),
      "error"
    );
    throw error;
  }
}

async function compileTools(options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  if (options.clear !== false) clearOutput();
  const ownsProgress = !state.progress.active;
  if (ownsProgress) {
    beginProgress("전체 도구 컴파일", [{ label: "전체 도구 컴파일", status: "running" }]);
    setProgressInsight("전체 도구 컴파일", "generator, validator, checker와 기준 정답을 컴파일합니다.");
  }
  try {
    const result = await api(`/api/problems/${state.selectedProblem}/tools/compile`, {
      method: "POST",
      body: "{}",
    });
    appendOutput(JSON.stringify(result.labels || {}, null, 2));
    const count = Object.keys(result.labels || {}).length;
    if (ownsProgress) setProgressStep(0, "success", `${count}개 도구 컴파일`);
    showLastRun(
      "전체 도구 컴파일 완료",
      `${count}개 도구를 사용할 준비가 되었습니다.`,
      "success"
    );
    showResult("Tools compiled.", "summary success");
    return result;
  } catch (error) {
    const detail = normalizeErrorDetail(error.message);
    if (ownsProgress) setProgressStep(0, "error", detail);
    showLastRun(
      "전체 도구 컴파일 실패",
      formatOperationFailure(detail, [
        "대상: generator, validator, checker, 기준 정답",
      ]),
      "error"
    );
    throw error;
  }
}

async function streamRequest(path, body, options = {}) {
  if (options.clear !== false) clearOutput();
  state.lastStreamDetail = "";
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const errorBody = await response.json();
    throw new Error(normalizeErrorDetail(errorBody.detail || errorBody) || `HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop();
    for (const block of blocks) {
      if (!block.trim()) continue;
      const { event, data } = parseSseBlock(block);
      if (event === "log") {
        const detail = streamProgressDetail(data.message);
        state.lastStreamDetail = detail || data.message || "";
        setText("loadingTitle", options.progressTitle || "작업 진행 중");
        setText("loadingMessage", detail);
        if (state.progress.active) {
          setProgressInsight(options.progressTitle || "현재 작업", detail);
          if (!options.manualProgress) updateRunningProgressDetail(detail);
        }
        options.onLog?.(data.message, detail, data);
      }
      if (event === "result") finalResult = data;
      if (event === "error") throw new Error(normalizeErrorDetail(data.message));
    }
  }
  return finalResult;
}

async function generateData(profile = "hidden", options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  const ownsProgress = !state.progress.active;
  if (ownsProgress) {
    beginProgress(`${profile} 데이터 생성`, [{ label: `${profile} 데이터 생성+검증`, status: "running" }]);
  }
  try {
    const result = await streamRequest(
      `/api/problems/${state.selectedProblem}/generate/stream`,
      { profile, force: false },
      { ...options, progressTitle: `${profile} 데이터 생성+검증` }
    );
    appendOutput(JSON.stringify(result, null, 2));
    if (ownsProgress) setProgressStep(0, "success", `${result.caseCount}개 데이터 생성 및 검증`);
    showLastRun(
      `${profile} 데이터 생성 완료`,
      `${result.caseCount}개 ${profile} case를 생성하고 검증했습니다.`,
      "success"
    );
    showResult(`Generated ${result.caseCount} ${profile} case(s).`, "summary success");
    return result;
  } catch (error) {
    const detail = normalizeErrorDetail(error.message);
    if (ownsProgress) setProgressStep(0, "error", detail);
    showLastRun(
      `${profile} 데이터 생성 실패`,
      formatOperationFailure(detail, [
        `Profile: ${profile}`,
        state.lastStreamDetail ? `마지막 단계: ${state.lastStreamDetail}` : "",
        "관련 대상: generator/cases.yml, generator/generator.cpp, validator/validator.cpp",
      ]),
      "error"
    );
    throw error;
  }
}

async function validateAllData(options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  const ownsProgress = !state.progress.active;
  if (ownsProgress) {
    beginProgress("모든 데이터 생성+검증", [{ label: "모든 데이터 생성+검증", status: "running" }]);
  }
  try {
    const result = await streamRequest(
      `/api/problems/${state.selectedProblem}/validate/stream`,
      { force: options.force === true },
      { ...options, progressTitle: "모든 데이터 생성+검증" }
    );
    appendOutput(JSON.stringify(result, null, 2));
    const profileCount = result.profileCount || 0;
    const caseCount = result.caseCount || 0;
    if (ownsProgress) setProgressStep(0, "success", `${profileCount}개 profile · ${caseCount}개 데이터 검증`);
    showLastRun(
      "모든 데이터 생성+검증 완료",
      `${profileCount}개 profile의 ${caseCount}개 데이터를 생성하고 검증했습니다.`,
      "success"
    );
    showResult(`Validated ${caseCount} case(s).`, "summary success");
    return result;
  } catch (error) {
    const detail = normalizeErrorDetail(error.message);
    if (ownsProgress) setProgressStep(0, "error", detail);
    showLastRun(
      "모든 데이터 생성+검증 실패",
      formatOperationFailure(detail, [
        state.lastStreamDetail ? `마지막 단계: ${state.lastStreamDetail}` : "",
        "관련 대상: generator/cases.yml, generator/generator.cpp, validator/validator.cpp",
      ]),
      "error"
    );
    throw error;
  }
}

async function verifySolutions(options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  const allPaths = solutionFilePaths();
  const requestedPaths = pathsNeedingSolutionVerification(options);
  if (!requestedPaths.length && state.lastSolutionVerification) {
    const cached = state.lastSolutionVerification;
    showLastRun(
      "솔루션 기대 결과 검증 생략",
      `${cached.checks?.length || 0}개 솔루션은 변경된 소스가 없어 기존 결과를 유지했습니다.`,
      cached.passed ? "success" : "error"
    );
    renderSolutionValidationSummary();
    renderTabFiles();
    return cached;
  }
  const partial = await streamRequest(
    `/api/problems/${state.selectedProblem}/solutions/verify/stream`,
    {
      profile: "hidden",
      solutions: requestedPaths.length === allPaths.length ? null : requestedPaths,
    },
    { ...options, progressTitle: "솔루션 기대 결과 검증" }
  );
  clearSolutionDirty(requestedPaths);
  const result =
    requestedPaths.length === allPaths.length
      ? { ...partial, incremental: false, complete: true, totalCount: allPaths.length }
      : mergeSolutionVerification(state.lastSolutionVerification, partial);
  const currentRunPassed = Boolean(partial.passed);
  state.lastSolutionVerification = result;
  persistProblemLastResult({
    solutionVerification: result,
    dirtySolutionPaths: state.dirtySolutionPaths,
  });
  renderSolutionValidationSummary();
  renderTabFiles();
  if (!currentRunPassed && !options.silentFailureAlert) {
    const failedCount = failedSolutionChecks(partial).length;
    showAlert(`기대 결과와 다른 솔루션 ${failedCount}개를 찾았습니다. 각 솔루션의 채점 결과에서 상세를 확인하세요.`, "error", {
      title: "솔루션 기대 결과 검증 실패",
      timeout: 5000,
    });
  }
  appendOutput(JSON.stringify(result, null, 2));
  const failureSummary = formatSolutionFailureSummary(currentRunPassed ? result : partial);
  const passedSummary = result.incremental
    ? `${requestedPaths.length}개 솔루션을 개별 테스트했습니다.${
        result.maintainedCount ? ` 기존 결과 ${result.maintainedCount}개를 함께 유지했습니다.` : ""
      }`
    : `${result.checks?.length || 0}개 솔루션이 기대 결과와 일치합니다.`;
  showLastRun(
    currentRunPassed ? "솔루션 기대 결과 검증 완료" : "솔루션 기대 결과 확인 필요",
    currentRunPassed ? passedSummary : failureSummary,
    currentRunPassed ? "success" : "error"
  );
  if (currentRunPassed) showResult("Solutions verified.", "summary success");
  return result;
}

async function verifySingleSolution(path) {
  return verifySolutions({ paths: [path], clear: false });
}

async function runAllChecks() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  clearOutput();
  const steps = [
    { label: "cases.yml 검사", status: "running" },
    { label: "도구 컴파일", status: "pending" },
    { label: "모든 데이터 생성+검증", status: "pending" },
    { label: "기대 결과 솔루션 검증", status: "pending" },
  ];
  beginProgress(`전체 테스트 · ${state.selectedProblem}번 문제`, steps);
  try {
    setProgressInsight("cases.yml 검사", "케이스 정의와 반복 규칙을 확인합니다.");
    setProgressStep(0, "running");
    const cases = await compileCases({ clear: false });
    setProgressStep(0, "success", `${cases.profiles?.length || 0}개 profile 확인`);

    setProgressInsight("도구 컴파일", "generator, validator, checker와 기준 정답을 컴파일합니다.");
    setProgressStep(1, "running");
    const tools = await compileTools({ clear: false });
    setProgressStep(1, "success", `${Object.keys(tools.labels || {}).length}개 도구 컴파일`);

    setProgressInsight(
      "모든 데이터 생성+검증",
      "sample/hidden을 포함한 모든 profile 데이터를 생성하고 validator로 확인합니다."
    );
    setProgressStep(2, "running");
    const validation = await validateAllData({ clear: false });
    setProgressStep(
      2,
      "success",
      `${validation.profileCount || 0}개 profile · ${validation.caseCount || 0}개 데이터 검증`
    );

    setProgressInsight("기대 결과 솔루션 검증", "등록된 솔루션의 실제 결과가 파일명 기대값과 맞는지 확인합니다.");
    setProgressStep(3, "running");
    const verification = await verifySolutions({ clear: false, silentFailureAlert: true });
    setProgressStep(
      3,
      verification.passed ? "success" : "error",
      verification.passed
        ? `${verification.checks?.length || 0}개 솔루션 확인`
        : `${failedSolutionChecks(verification).length}개 솔루션 기대 결과 불일치`
    );

    const summary = [
      `${cases.profiles?.length || 0}개 profile 확인`,
      `${Object.keys(tools.labels || {}).length}개 도구 컴파일`,
      `${validation.profileCount || 0}개 profile · ${validation.caseCount || 0}개 데이터 검증`,
      `${verification.checks?.length || 0}개 솔루션 검증`,
    ].join(" · ");
    const solutionFailureSummary = formatSolutionFailureSummary(verification);
    setProgressInsight(
      verification.passed ? "전체 테스트 통과" : "수정할 항목이 있습니다",
      verification.passed
        ? summary
        : solutionFailureSummary
    );
    showLastRun(
      verification.passed ? "전체 테스트 완료" : "전체 테스트 실패",
      verification.passed ? summary : solutionFailureSummary,
      verification.passed ? "success" : "error"
    );
    if (verification.passed) {
      state.lastFullTest = {
        passed: true,
        summary,
        checkedAt: Date.now(),
        profile: "all",
      };
      persistProblemLastResult({
        fullTest: state.lastFullTest,
        dirtyAfterFullTest: false,
        dirtyReason: "",
      });
      updateBuildPanel();
      renderTabFiles();
      showResult("전체 테스트가 완료되었습니다.", "summary success");
    } else {
      state.lastFullTest = {
        passed: false,
        summary: solutionFailureSummary,
        checkedAt: Date.now(),
        profile: "all",
      };
      persistProblemLastResult({
        fullTest: state.lastFullTest,
        dirtyAfterFullTest: true,
        dirtyReason: "전체 테스트가 실패했습니다.",
      });
      updateBuildPanel();
      renderTabFiles();
      const failedCount = failedSolutionChecks(verification).length;
      showAlert(`솔루션 기대 결과가 ${failedCount}개 일치하지 않습니다. 각 솔루션의 채점 결과에서 상세를 확인하세요.`, "error", {
        title: "전체 테스트 실패",
        timeout: 5000,
      });
    }
  } catch (error) {
    const runningIndex = state.progress.steps.findIndex((step) => step.status === "running");
    const failedStep = runningIndex >= 0 ? state.progress.steps[runningIndex]?.label : "";
    const detail = normalizeErrorDetail(error.message);
    if (runningIndex >= 0) setProgressStep(runningIndex, "error", detail);
    setProgressInsight(
      "수정할 항목이 있습니다",
      detail || "실패한 단계를 확인한 뒤 다시 실행하세요."
    );
    showLastRun(
      "전체 테스트 실패",
      formatOperationFailure(detail, [
        failedStep ? `실패 단계: ${failedStep}` : "",
        state.lastStreamDetail ? `마지막 단계: ${state.lastStreamDetail}` : "",
        "관련 대상: cases.yml, generator, validator, checker, solutions",
      ]),
      "error"
    );
    throw error;
  }
}

async function buildPack() {
  $("packIdInput").value = $("packIdInput").value.trim() || "basic";
  $("packVerifyProfileInput").value = $("packVerifyProfileInput").value.trim() || "hidden";
  await saveOpenFileIfDirty();
  if (!hasFreshFullTest()) {
    showAlert("팩 빌드 전에 전체 테스트를 자동으로 실행합니다.", "info", {
      title: "팩 빌드 준비",
      timeout: 5000,
    });
    await runAllChecksOnce();
    if (!hasFreshFullTest()) {
      throw new Error("전체 테스트를 통과하지 못해 팩 빌드를 중단했습니다.");
    }
  }
  return startPackBuildOnce();
}

function bulkProblemIds() {
  return (state.problems || []).map((problem) => problem.problemId).filter(Boolean);
}

function selectedBulkProblemIdsFromModal() {
  return Array.from(document.querySelectorAll("[data-bulk-problem]:checked"))
    .map((input) => input.value)
    .filter(Boolean);
}

function bulkMaxWorkersFromModal() {
  const value = Number.parseInt(optional("bulkMaxWorkersInput")?.value || "", 10);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function updateBulkStartButton() {
  const button = optional("workspaceBuildStartButton");
  if (!button) return;
  const selectedCount = selectedBulkProblemIdsFromModal().length;
  button.disabled = selectedCount === 0 || document.body.getAttribute("aria-busy") === "true";
  button.textContent = selectedCount
    ? `선택한 ${selectedCount}개 문제로 팩 빌드`
    : "문제를 선택하세요";
}

function renderBulkProblemList() {
  const list = $("bulkProblemList");
  const problems = state.problems || [];
  if (!problems.length) {
    list.innerHTML = `<p class="muted">등록된 문제가 없습니다.</p>`;
    updateBulkStartButton();
    return;
  }
  list.innerHTML = problems
    .map(
      (problem) => `
        <label class="bulk-problem-option">
          <input type="checkbox" data-bulk-problem value="${escapeHtml(problem.problemId)}" checked />
          <span class="bulk-problem-copy">
            <strong>${escapeHtml(problem.problemId)} ${escapeHtml(problem.title || "")}</strong>
            <small>버전 ${escapeHtml(problem.version || "-")} · ${escapeHtml(problem.defaultProfile || "-")}</small>
          </span>
        </label>
      `
    )
    .join("");
  for (const input of document.querySelectorAll("[data-bulk-problem]")) {
    input.addEventListener("change", updateBulkStartButton);
  }
  updateBulkStartButton();
}

function openWorkspaceBuildModal() {
  if (!bulkProblemIds().length) throw new Error("빌드할 문제가 없습니다.");
  $("bulkPackIdInput").value = optional("packIdInput")?.value.trim() || "basic";
  $("bulkVerifyProfileInput").value = optional("packVerifyProfileInput")?.value.trim() || "hidden";
  $("bulkMaxWorkersInput").value = "";
  renderBulkProblemList();
  openModal("workspaceBuildModal");
}

function updateBulkProgressFromLog(message, problemIds) {
  const match = String(message || "").match(/^\[(\d+)\/(\d+)] Problem ([^:]+):\s*(.*)$/);
  if (!match) return;
  const problemId = match[3];
  const detail = streamProgressDetail(match[4]);
  const index = problemIds.indexOf(problemId);
  if (index < 0) return;
  const status = match[4].startsWith("Failed:") || match[4].startsWith("Full test failed:")
    ? "error"
    : match[4].startsWith("Pack built:")
      ? "success"
      : "running";
  setProgressStep(index, status, detail);
  setProgressInsight(`${problemId} 문제`, detail);
}

function persistBulkProblemResult(item, checkedAt) {
  const problemId = item?.problemId;
  if (!problemId) return;
  const fullTest = {
    passed: Boolean(item.passed),
    summary: item.summary || "",
    checkedAt,
    profile: "all",
  };
  const patch = {
    fullTest,
    dirtyAfterFullTest: !item.passed,
    dirtyReason: item.passed ? "" : item.summary || "전체 문제 테스트가 실패했습니다.",
  };
  if (item.pack) {
    patch.lastPackResult = {
      ...item.pack,
      finishedAt: checkedAt,
    };
  }
  persistProblemLastResult(patch, problemId);
}

function applyBulkBuildResult(result) {
  const checkedAt = Date.now();
  for (const item of result.problems || []) {
    persistBulkProblemResult(item, checkedAt);
  }
  if (state.selectedProblem) restoreProblemLastResult(state.selectedProblem);
  renderProblems(state.problems);
  renderTabFiles();
  updateBuildPanel();
}

function bulkBuildSummary(result) {
  const failed = result.failedCount || 0;
  const total = result.problemCount || 0;
  const packs = result.packCount || 0;
  if (!failed) return `${total}개 문제 전체 테스트 통과 · ${packs}개 팩 생성`;
  const failedProblems = (result.problems || [])
    .filter((item) => !item.passed)
    .slice(0, 4)
    .map((item) => `${item.problemId}: ${item.summary || "실패"}`)
    .join("\n");
  const remaining = failed > 4 ? `\n외 ${failed - 4}개 문제 실패` : "";
  const packSummary = packs ? `${packs}개 팩 생성` : "팩 생성 안 함";
  return `${total}개 중 ${failed}개 문제 실패 · ${packSummary}\n${failedProblems}${remaining}`;
}

async function buildAllPacks(problemIds = bulkProblemIds()) {
  if (!problemIds.length) throw new Error("빌드할 문제가 없습니다.");
  const packId = optional("bulkPackIdInput")?.value.trim()
    || optional("packIdInput")?.value.trim()
    || "basic";
  const verifyProfile = optional("bulkVerifyProfileInput")?.value.trim()
    || optional("packVerifyProfileInput")?.value.trim()
    || "hidden";
  await saveOpenFileIfDirty();
  beginProgress(
    "전체 문제 테스트/팩 빌드",
    problemIds.map((problemId) => ({ label: `${problemId} 테스트/팩`, status: "pending" }))
  );
  const result = await streamRequest(
    "/api/workspace/packs/build-all/stream",
    {
      pack_id: packId,
      verify_profile: verifyProfile,
      force: false,
      max_workers: bulkMaxWorkersFromModal(),
      problem_ids: problemIds,
    },
    {
      clear: false,
      manualProgress: true,
      progressTitle: "전체 문제 테스트/팩 빌드",
      onLog: (message) => updateBulkProgressFromLog(message, problemIds),
    }
  );
  for (const [index, item] of (result.problems || []).entries()) {
    setProgressStep(index, item.passed ? "success" : "error", item.summary || "");
  }
  setProgressInsight(result.passed ? "전체 문제 팩 빌드 완료" : "수정할 문제가 있습니다", bulkBuildSummary(result));
  applyBulkBuildResult(result);
  showLastRun(
    result.passed ? "전체 문제 테스트/팩 빌드 완료" : "전체 문제 테스트/팩 빌드 실패",
    bulkBuildSummary(result),
    result.passed ? "success" : "error"
  );
  showAlert(bulkBuildSummary(result), result.passed ? "success" : "error", {
    title: result.passed ? "전체 문제 팩 빌드 완료" : "전체 문제 테스트 실패",
    timeout: result.passed ? 6500 : 10000,
  });
  return result;
}

async function buildAllPacksOnce(problemIds = bulkProblemIds()) {
  if (state.activePackJob) throw new Error("팩 빌드 진행 중에는 전체 문제 빌드를 시작할 수 없습니다.");
  return withProblemTaskLock(async () => {
    const lease = acquireRunAllLease("전체 문제");
    if (!lease) throw new Error("이미 다른 탭에서 전체 테스트가 실행 중입니다.");
    try {
      return await buildAllPacks(problemIds);
    } finally {
      releaseRunAllLease(lease);
    }
  });
}

function packJobSummary(job) {
  if (!job) return "";
  return [
    job.problemId ? `${job.problemId} 문제` : "",
    job.packId ? `Pack ${job.packId}` : "",
    job.outputDir || "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function persistPackJob(job, problemId, details = {}) {
  const previous = state.activePackJob || {};
  state.activePackJob = {
    jobId: job.jobId,
    problemId,
    packId: details.packId || previous.packId,
    outputDir: details.outputDir || previous.outputDir,
    startedAt: previous.startedAt || Date.now(),
  };
  writeStorage(PACK_JOB_KEY, state.activePackJob);
  showLastRun(
    "팩 빌드 진행 중",
    `${packJobSummary(state.activePackJob)} · 완료되면 자동으로 알려드립니다.`,
    "running",
    { problemId }
  );
  updateGlobalActionState();
  updateBuildPanel();
}

function clearPackJob() {
  state.activePackJob = null;
  removeStorage(PACK_JOB_KEY);
  if (state.packPollTimer) {
    window.clearTimeout(state.packPollTimer);
    state.packPollTimer = null;
  }
  updateGlobalActionState();
  updateBuildPanel();
}

async function startPackBuild() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  await saveOpenFileIfDirty();
  if (!hasFreshFullTest()) {
    throw new Error("팩 빌드 전 현재 문제의 전체 테스트를 먼저 통과해야 합니다.");
  }
  const problemId = state.selectedProblem;
  const packId = $("packIdInput").value.trim();
  const outputDir = PACK_OUTPUT_DIR;
  const verifyProfile = $("packVerifyProfileInput").value.trim() || "hidden";
  if (!packId) throw new Error("Pack ID를 입력하세요.");
  if (state.activePackJob) throw new Error("이미 팩 빌드가 진행 중입니다.");
  if (currentRunAllLock()) throw new Error("전체 테스트 진행 중에는 팩 빌드를 시작할 수 없습니다.");
  const job = await api(`/api/problems/${encodeURIComponent(problemId)}/packs/build`, {
    method: "POST",
    body: JSON.stringify({
      pack_id: packId,
      verify_profile: verifyProfile,
    }),
  });
  persistPackJob(job, problemId, { packId, outputDir });
  updateBuildPanel();
  showResult(`${problemId} 문제 팩 빌드를 백그라운드에서 시작했습니다.`, "summary success");
  schedulePackJobPoll(problemId, job.jobId, 500);
}

async function startPackBuildOnce() {
  return withProblemTaskLock(startPackBuild);
}

function schedulePackJobPoll(problemId, jobId, delay = 1500) {
  if (state.packPollTimer) window.clearTimeout(state.packPollTimer);
  state.packPollTimer = window.setTimeout(() => {
    void pollPackJob(problemId, jobId);
  }, delay);
}

async function pollPackJob(problemId, jobId) {
  try {
    const job = await api(
      `/api/problems/${encodeURIComponent(problemId)}/packs/jobs/${encodeURIComponent(jobId)}`
    );
    if (job.status === "succeeded") {
      clearPackJob();
      const label = job.result?.archiveLabel || "팩 파일";
      const packResult = {
        ...job.result,
        downloadUrl: `/api/problems/${encodeURIComponent(problemId)}/packs/jobs/${encodeURIComponent(jobId)}/download`,
        finishedAt: Date.now(),
      };
      state.lastPackResult = packResult;
      persistProblemLastResult({ lastPackResult: packResult }, problemId);
      updateBuildPanel();
      showLastRun("팩 빌드 완료", `${problemId} 문제 팩이 생성되었습니다: ${label}`, "success", {
        problemId,
      });
      showResult(`팩 빌드 완료: ${label}`, "summary success");
      return;
    }
    if (job.status === "failed") {
      clearPackJob();
      const detail = normalizeErrorDetail(job.error);
      showLastRun(
        "팩 빌드 실패",
        formatOperationFailure(detail, [
          "작업: 팩 빌드",
          packJobSummary(job) ? `빌드 정보: ${packJobSummary(job)}` : "",
        ]),
        "error",
        { problemId }
      );
      showAlert(detail, "error", { title: "팩 빌드 실패", timeout: 10000 });
      return;
    }
    persistPackJob(job, problemId);
    schedulePackJobPoll(problemId, jobId);
  } catch (error) {
    clearPackJob();
    showAlert(error.message, "error", { title: "팩 빌드 상태 확인 실패", timeout: 9000 });
  }
}

function syncPackJobFromStorage() {
  const job = readStorage(PACK_JOB_KEY);
  if (!job?.jobId || !job?.problemId) {
    state.activePackJob = null;
    if (state.packPollTimer) {
      window.clearTimeout(state.packPollTimer);
      state.packPollTimer = null;
    }
    updateGlobalActionState();
    return;
  }
  const alreadyPolling = state.activePackJob?.jobId === job.jobId && state.packPollTimer;
  state.activePackJob = job;
  updateGlobalActionState();
  if (!alreadyPolling) schedulePackJobPoll(job.problemId, job.jobId, 250);
}

function openSolutionCreateModal() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  initializeSourceModalEditors();
  $("solutionCreateName").value = "wrong_solution";
  $("solutionCreateExpected").value = "wa";
  $("solutionCreateLanguage").value = "cpp";
  setModalEditorValue("create", "");
  updateSolutionPreview();
  openModal("solutionCreateModal");
  refreshModalEditor("create");
}

async function openSolutionEditModal(path) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  initializeSourceModalEditors();
  const source =
    path === state.selectedFile
      && state.selectedTab !== "solutions"
      ? getEditorValue()
      : (
          await api(
            `/api/problems/${encodeURIComponent(state.selectedProblem)}/files/${apiFilePath(path)}`
          )
        ).content;
  state.editingSolutionPath = path;
  const parts = solutionParts(path);
  setText("solutionEditPath", path);
  $("solutionName").value = parts.name;
  $("solutionExpected").value = parts.expected;
  $("solutionLanguage").value = parts.language;
  setModalEditorValue("edit", source || "");
  updateSolutionRenamePreview();
  openModal("solutionEditModal");
  refreshModalEditor("edit");
}

function openSolutionUpload() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  const input = $("solutionUploadInput");
  input.disabled = false;
  input.value = "";
  input.click();
}

function openSolutionCasesModal(path) {
  const check = solutionCheckForPath(path);
  if (!check) {
    throw new Error("아직 표시할 채점 결과가 없습니다. 개별 테스트나 기대 결과 검증을 먼저 실행하세요.");
  }
  setText("solutionCasesTitle", path);
  setText("solutionCasesSubtitle", `${roleForFile(path)} · ${statusLabelForResult(check.expectedStatus)} 기대`);
  $("solutionCasesBody").innerHTML = renderSolutionCasesBody(check);
  openModal("solutionCasesModal");
}

async function uploadSolutions(files) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  if (!files.length) return;
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const result = await api(`/api/problems/${encodeURIComponent(state.selectedProblem)}/solutions/upload`, {
    method: "POST",
    body: form,
  });
  state.files = result.files || state.files;
  const uploaded = result.uploaded || [];
  for (const item of uploaded) removeSolutionChecks([item.path]);
  setDirtySolutionPaths([
    ...state.dirtySolutionPaths,
    ...uploaded.map((item) => item.path),
  ]);
  markFullTestDirty("솔루션 업로드로 전체 테스트가 다시 필요합니다.");
  renderTaskPanel();
  showResult(`${uploaded.length} solution file(s) uploaded.`, "summary success");
}

async function createSolution() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  if (!updateSolutionPreview()) {
    $("solutionCreateName").focus();
    throw new Error("솔루션 이름을 확인하세요.");
  }
  const result = await api(`/api/problems/${state.selectedProblem}/solutions/create`, {
    method: "POST",
    body: JSON.stringify({
      name: $("solutionCreateName").value.trim(),
      expected: $("solutionCreateExpected").value,
      language: $("solutionCreateLanguage").value,
    }),
  });
  const customSource = getModalEditorValue("create");
  if (customSource.trim()) {
    await api(
      `/api/problems/${encodeURIComponent(state.selectedProblem)}/files/${apiFilePath(result.created.path)}`,
      {
        method: "PUT",
        body: JSON.stringify({ content: customSource }),
      }
    );
  }
  state.files = result.files || state.files;
  markSolutionDirty(result.created.path, "새 솔루션이 추가되어 검증이 필요합니다.");
  selectSolutionPath(result.created.path);
  renderTaskPanel();
  closeModals();
  showResult("새 솔루션 파일을 만들었습니다.", "summary success");
}

async function renameSolution() {
  const oldPath = state.editingSolutionPath || state.selectedFile;
  if (!state.selectedProblem || !oldPath?.startsWith("solutions/")) {
    throw new Error("편집할 솔루션 파일을 먼저 선택하세요.");
  }
  if (!updateSolutionRenamePreview()) {
    $("solutionName").focus();
    throw new Error("솔루션 이름을 확인하세요.");
  }
  const result = await api(`/api/problems/${state.selectedProblem}/solutions/rename`, {
    method: "PATCH",
    body: JSON.stringify({
      path: oldPath,
      name: $("solutionName").value.trim(),
      expected: $("solutionExpected").value,
      language: $("solutionLanguage").value,
    }),
  });
  const nextPath = result.renamed.path;
  await api(
    `/api/problems/${encodeURIComponent(state.selectedProblem)}/files/${apiFilePath(nextPath)}`,
    {
      method: "PUT",
      body: JSON.stringify({ content: getModalEditorValue("edit") }),
    }
  );
  state.files = result.files || state.files;
  if (state.detail && result.metadata) state.detail.metadata = result.metadata;
  markSolutionDirty(nextPath, "솔루션 변경으로 재검증이 필요합니다.", { oldPath });
  selectSolutionPath(nextPath);
  renderTaskPanel();
  closeModals();
  showResult("솔루션을 저장했습니다.", "summary success");
}

function openModal(id, trigger = document.activeElement) {
  state.activeModalTrigger = trigger instanceof HTMLElement ? trigger : null;
  const modal = optional(id);
  modal?.classList.remove("hidden");
  const firstField = modal?.querySelector("input, select, textarea");
  if (firstField instanceof HTMLElement) firstField.focus();
}

function activeCodeEditorElement(event) {
  const target = event?.target instanceof Element ? event.target : null;
  const active = document.activeElement instanceof Element ? document.activeElement : null;
  return (
    target?.closest(".CodeMirror, .source-modal-editor, #fileEditor")
    || active?.closest(".CodeMirror, .source-modal-editor, #fileEditor")
  );
}

function closeModals() {
  optional("newProblemModal")?.classList.add("hidden");
  optional("deleteProblemModal")?.classList.add("hidden");
  optional("packBuildModal")?.classList.add("hidden");
  optional("solutionCreateModal")?.classList.add("hidden");
  optional("solutionEditModal")?.classList.add("hidden");
  optional("workspaceBuildModal")?.classList.add("hidden");
  optional("solutionCasesModal")?.classList.add("hidden");
  state.editingSolutionPath = null;
  state.activeModalTrigger?.focus();
  state.activeModalTrigger = null;
}

function bindEvents() {
  $("fileEditor").addEventListener("input", handleEditorInput);
  $("fileEditor").addEventListener("beforeinput", handleEditorBeforeInput);
  $("fileEditor").addEventListener("keydown", handleEditorKeydown);
  $("fileEditor").addEventListener("keyup", updateEditorStatus);
  $("fileEditor").addEventListener("click", updateEditorStatus);
  $("fileEditor").addEventListener("select", updateEditorStatus);
  $("fileEditor").addEventListener("scroll", syncEditorScroll);
  $("fileEditor").addEventListener("compositionstart", handleEditorCompositionStart);
  $("fileEditor").addEventListener("compositionend", handleEditorCompositionEnd);
  optional("editorCommandInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeEditorCommandLine();
      focusEditor();
    }
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      submitEditorCommandLine();
    }
  });
  $("editorSettingsButton").addEventListener("click", (event) => {
    event.stopPropagation();
    setEditorSettingsOpen(!state.editorSettingsOpen);
  });
  $("editorSettingsPanel").addEventListener("click", (event) => {
    event.stopPropagation();
  });
  for (const button of document.querySelectorAll("[data-editor-mode]")) {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      setEditorMode(button.dataset.editorMode, {
        modalEditorKey: modalEditorKeyForElement(button),
      });
    });
  }
  $("sidebarToggle").addEventListener("click", toggleSidebar);
  $("sidebarClose").addEventListener("click", closeSidebar);
  $("sidebarBackdrop").addEventListener("click", closeSidebar);
  $("newProblemButton").addEventListener("click", () => openModal("newProblemModal"));
  $("workspaceBuildAllButton").addEventListener("click", () => {
    void withErrors(openWorkspaceBuildModal, "전체 문제 팩 빌드를 준비하는 중입니다.");
  });
  $("bulkSelectAllButton").addEventListener("click", () => {
    for (const input of document.querySelectorAll("[data-bulk-problem]")) input.checked = true;
    updateBulkStartButton();
  });
  $("workspaceBuildStartButton").addEventListener("click", () => {
    const problemIds = selectedBulkProblemIdsFromModal();
    closeModals();
    void withErrors(
      () => buildAllPacksOnce(problemIds),
      "전체 문제 테스트/팩 빌드를 실행하는 중입니다."
    );
  });
  $("createProblemButton").addEventListener("click", () => {
    void withErrors(createProblem, "문제를 생성하는 중입니다.");
  });
  $("deleteProblemConfirmInput").addEventListener("input", updateDeleteProblemButton);
  $("deleteProblemButton").addEventListener("click", () => {
    void withErrors(deleteSelectedProblem, "문제를 삭제하는 중입니다.");
  });
  $("saveFileButton").addEventListener("click", () => {
    void withErrors(saveFile, "파일을 저장하는 중입니다.");
  });
  optional("runAllButton")?.addEventListener("click", () => {
    void withErrors(runAllChecksOnce, "전체 테스트를 실행하는 중입니다.");
  });
  optional("packButton")?.addEventListener("click", () => {
    void withInlineErrors(buildPack);
  });
  optional("packStartButton")?.addEventListener("click", () => {
    void withInlineErrors(buildPack);
  });
  optional("lastRunClose")?.addEventListener("click", () => {
    hideLastRunPanel();
  });
  $("solutionCreateButton").addEventListener("click", () => {
    void withErrors(createSolution, "솔루션 파일을 생성하는 중입니다.");
  });
  $("solutionRenameButton").addEventListener("click", () => {
    void withErrors(renameSolution, "솔루션 파일명을 변경하는 중입니다.");
  });
  for (const id of ["solutionCreateName", "solutionCreateExpected", "solutionCreateLanguage"]) {
    $(id).addEventListener("input", updateSolutionPreview);
    $(id).addEventListener("change", updateSolutionPreview);
  }
  for (const id of ["solutionName", "solutionExpected", "solutionLanguage"]) {
    $(id).addEventListener("input", updateSolutionRenamePreview);
    $(id).addEventListener("change", updateSolutionRenamePreview);
  }
  for (const id of [
    "metadataProblemIdInput",
    "metadataTitle",
    "metadataFolder",
    "metadataVersion",
    "metadataDefaultProfile",
    "metadataCompileTimeout",
    "metadataGenerationTimeout",
    "metadataSolutionTimeout",
    "metadataUserTimeout",
    "metadataToolGenerator",
    "metadataToolGeneratorConfig",
    "metadataToolValidator",
    "metadataToolChecker",
    "metadataToolSolution",
  ]) {
    $(id).addEventListener("input", updateMetadataPreview);
    $(id).addEventListener("change", updateMetadataPreview);
  }
  for (const id of ["packIdInput", "packVerifyProfileInput"]) {
    $(id).addEventListener("input", updateBuildDashboard);
    $(id).addEventListener("change", updateBuildDashboard);
  }
  $("resourceFilterInput").addEventListener("input", (event) => {
    state.resourceFilters[state.selectedTab] = event.target.value;
    renderTabFiles();
  });
  $("solutionUploadInput").addEventListener("change", (event) => {
    void withErrors(async () => {
      await uploadSolutions(Array.from(event.target.files || []));
      event.target.value = "";
    }, "솔루션 파일을 업로드하는 중입니다.");
  });
  for (const button of document.querySelectorAll(".tab-button")) {
    button.addEventListener("click", () => {
      void withErrors(() => selectTab(button.dataset.tab), "탭을 불러오는 중입니다.");
    });
  }
  for (const button of document.querySelectorAll("[data-modal-close]")) {
    button.addEventListener("click", closeModals);
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (activeCodeEditorElement(event) && state.editorMode === "vim") return;
      setEditorSettingsOpen(false);
      closeModals();
      closeSidebar();
    }
  });
  document.addEventListener("click", () => {
    if (state.editorSettingsOpen) setEditorSettingsOpen(false);
  });
  window.addEventListener("beforeunload", (event) => {
    if (!hasUnsavedChanges()) return;
    event.preventDefault();
    event.returnValue = "";
  });
  window.addEventListener("storage", (event) => {
    if (event.key === RUN_ALL_LOCK_KEY) updateGlobalActionState();
    if (event.key === PACK_JOB_KEY) syncPackJobFromStorage();
    if (event.key === LAST_RESULTS_KEY && state.selectedProblem) {
      restoreProblemLastResult(state.selectedProblem);
      renderTaskPanel();
    }
  });
  runAllChannel?.addEventListener("message", (event) => {
    if (event.data?.type === "run-all-lock-changed") updateGlobalActionState();
  });
}

initializeCodeMirror();
initializeSourceModalEditors();
bindEvents();
restoreEditorSettings();
updateSolutionPreview();
syncPackJobFromStorage();
updateGlobalActionState();
withErrors(refresh, "워크스페이스를 불러오는 중입니다.");
