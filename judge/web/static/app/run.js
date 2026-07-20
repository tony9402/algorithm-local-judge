/**
 * 실행 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;
function runFormData(profile) {
  const formData = new FormData();
  formData.append("problem_id", app.$("problemSelect").value);
  formData.append("profile", profile || app.judgeProfile());
  formData.append("source_mode", "text");
  formData.append("filename", app.$("filenameInput").value.trim());
  formData.append("language", app.$("languageHint").value);
  formData.append("source_text", app.$("sourceTextInput").value);
  return formData;
}
async function streamRun(formData, onQueued) {
  return app.runQueuedJob("/api/run/jobs", {
    method: "POST",
    body: formData,
    onQueued,
  });
}

function resultCaseCount(result) {
  if (Number.isFinite(result.caseCount)) return result.caseCount;
  return result.cases?.length || 0;
}
async function restoreRunResult(result) {
  state.lastRunResult = result;
  state.artifacts = null;
  app.$("wrongPanel").classList.add("hidden");
  app.hideGenerationProgress();
  app.setBadge(app.verdictLabel(result.status), statusClassName(result.status));
  app.setText("resultMeta", `${result.problemId} · ${app.profileLabel(result.profile)} · ${result.language} · ${result.runId}`);
  app.setStatusCard("data", "준비됨", app.profileLabel(result.profile));
  app.setStatusCard(
    "judge",
    app.verdictLabel(result.status),
    app.profileCaseText(resultCaseCount(result), result.profile)
  );
  app.setStatusCard("run", result.runId, runMetricsText(result));
  app.setSummary(
    runSummary(result),
    result.status === "accepted" ? "result-summary success" : "result-summary error"
  );
  renderLastResultAnchor(result);
  if (result.firstFailedCase) {
    await loadWrongCase(result.runId, result.firstFailedCase);
  }
}
/**
 * 제출 실행에 필요한 입력을 준비하고 외부 프로세스나 서비스 호출을 수행합니다.
 */
async function runSubmission(profile = app.judgeProfile()) {
  state.artifacts = null;
  app.$("wrongPanel").classList.add("hidden");
  app.$("caseResults").classList.add("hidden");
  app.clearDebugLog();
  app.setBadge("채점 중", "neutral");
  app.setStatusCard("data", "확인 중", app.profileLabel(profile));
  app.setStatusCard("judge", "대기 중");
  app.setStatusCard("run", "-", "진행 중");
  app.setSummary(`${app.profileLabel(profile)} 테스트케이스로 채점 중입니다.`, "result-summary");
  renderLastResultPending(profile);
  const compileResult = await app.compileCasesData({ showSuccess: false, profile });
  if (!compileResult.valid) {
    renderLastResultUnavailable("채점 준비를 완료하지 못했습니다.");
    return;
  }
  const totalCases = app.compiledCaseCount(compileResult);
  app.setGenerationProgress(0, totalCases, "데이터 생성");
  app.appendRunLog("채점을 시작합니다.");
  const problemId = app.$("problemSelect").value;
  const result = await streamRun(runFormData(profile), () => recordSubmissionCooldown(problemId));
  if (!result) throw new Error("채점 결과를 받지 못했습니다.");
  state.lastRunResult = result;
  app.setBadge(app.verdictLabel(result.status), statusClassName(result.status));
  app.setText("resultMeta", `${result.problemId} · ${app.profileLabel(result.profile)} · ${result.language} · ${result.runId}`);
  app.setStatusCard("data", "준비됨", app.profileLabel(result.profile));
  app.setStatusCard(
    "judge",
    app.verdictLabel(result.status),
    app.profileCaseText(resultCaseCount(result), result.profile)
  );
  app.setStatusCard("run", result.runId, runMetricsText(result));
  app.setSummary(runSummary(result), result.status === "accepted" ? "result-summary success" : "result-summary error");
  renderLastResultAnchor(result);
  if (result.message) state.debugLogs.push(result.message);
  app.renderDebugLog();
  if (result.firstFailedCase) {
    await loadWrongCase(result.runId, result.firstFailedCase);
  }
  await app.refreshSecondaryData();
}

function recordSubmissionCooldown(problemId, seconds = 5) {
  state.submissionCooldowns[problemId] = Date.now() + seconds * 1000;
  scheduleCooldownTick();
  app.updateActionState();
}

function submissionCooldownRemaining(problemId = app.$("problemSelect")?.value) {
  const until = state.submissionCooldowns[problemId] || 0;
  return Math.max(0, Math.ceil((until - Date.now()) / 1000));
}

function scheduleCooldownTick() {
  if (state.cooldownTimer) window.clearTimeout(state.cooldownTimer);
  state.cooldownTimer = window.setTimeout(() => {
    app.updateActionState();
    if (submissionCooldownRemaining() > 0) scheduleCooldownTick();
  }, 250);
}

function caseStatusLabel(status) {
  if (status === "ok") return "맞음";
  if (status === "wrong_answer") return "틀림";
  if (status === "runtime_error") return "런타임 오류";
  if (status === "time_limit") return "시간 초과";
  if (status === "memory_limit") return "메모리 초과";
  return status ? `알 수 없음 (${status})` : "-";
}

function renderCaseResults(result, targetId = "resultCaseResults") {
  const panel = app.optional(targetId);
  if (!panel) return;
  const cases = Array.isArray(result.cases) ? result.cases : [];
  if (!cases.length) {
    panel.classList.remove("hidden");
    panel.innerHTML = '<div class="modal-status muted">표시할 테스트케이스 결과가 없습니다.</div>';
    return;
  }
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div class="case-results-heading">
      <strong>테스트케이스 결과</strong>
      <span>${app.escapeHtml(String(cases.length))}개</span>
    </div>
    <div class="case-result-table">
      ${cases.map(renderCaseResultRow).join("")}
    </div>
  `;
}

function showResultModal(result) {
  state.lastRunResult = result;
  app.setText(
    "resultModalMeta",
    `${result.problemId || "-"} · ${app.profileLabel(result.profile)} · ${result.language || "-"} · ${result.runId || "-"}`
  );
  renderCaseResults(result, "resultCaseResults");
  app.openModal("resultModal");
}

function renderCaseResultRow(testCase) {
  const status = testCase.status || "";
  const failed = status && status !== "ok";
  const memory = Number.isFinite(testCase.memoryBytes)
    ? `${Math.round(testCase.memoryBytes / 1024)} KB`
    : "-";
  const artifactButton = failed
    ? `<button type="button" data-case-artifact="${app.escapeHtml(testCase.case)}">보기</button>`
    : "";
  return `
    <div class="case-result-row ${failed ? "failed" : "passed"}">
      <strong>${app.escapeHtml(testCase.case || "-")}</strong>
      <span>${app.escapeHtml(caseStatusLabel(status))}</span>
      <small>${app.escapeHtml(String(testCase.timeMs ?? "-"))} ms · ${app.escapeHtml(memory)}</small>
      <p>${app.escapeHtml(testCase.message || "")}</p>
      ${artifactButton}
    </div>
  `;
}

function statusClassName(status) {
  if (status === "accepted") return "accepted";
  if (status === "wrong_answer") return "wrong";
  if (status === "compile_error") return "compile";
  if (status === "runtime_error") return "runtime";
  if (status === "time_limit") return "time";
  if (status === "memory_limit") return "memory";
  return "neutral";
}
function runSummary(result) {
  const metrics = runMetricsText(result);
  if (result.status === "accepted") {
    return `${app.profileCaseText(resultCaseCount(result), result.profile)} 채점 완료. ${metrics}`;
  }
  const failed = result.firstFailedCase ? ` · 실패 케이스 ${result.firstFailedCase}` : "";
  return `${app.verdictLabel(result.status)}${failed}. ${metrics}`;
}
function runMetricsText(result) {
  const metrics = result.metrics || {};
  const time = metrics.maxTimeLabel || "확인 불가";
  const memory = metrics.maxMemoryLabel || "확인 불가";
  return `최대 시간 ${time} · 최대 메모리 ${memory}`;
}

function renderLastResultAnchor(result) {
  const anchor = app.optional("lastResultAnchor");
  if (!anchor || !result) return;
  anchor.classList.remove("hidden");
  app.setText("lastResultBadge", app.verdictLabel(result.status));
  const badge = app.optional("lastResultBadge");
  if (badge) badge.className = `badge ${statusClassName(result.status)}`;
  app.setText("lastResultMetrics", runMetricsText(result));
  const button = app.optional("lastResultButton");
  if (button) button.disabled = false;
}

function renderLastResultPending(profile) {
  const anchor = app.optional("lastResultAnchor");
  if (!anchor) return;
  anchor.classList.remove("hidden");
  app.setText("lastResultBadge", "채점 중");
  const badge = app.optional("lastResultBadge");
  if (badge) badge.className = "badge neutral";
  app.setText("lastResultMetrics", `${app.profileLabel(profile)} 테스트케이스를 준비하고 있습니다.`);
  const button = app.optional("lastResultButton");
  if (button) button.disabled = true;
}

function renderLastResultUnavailable(message) {
  app.setText("lastResultBadge", "준비 실패");
  const badge = app.optional("lastResultBadge");
  if (badge) badge.className = "badge wrong";
  app.setText("lastResultMetrics", message);
  const button = app.optional("lastResultButton");
  if (button) button.disabled = true;
}
/**
 * 오답 케이스을 파일이나 캐시에서 읽고 필요한 기본값을 적용합니다.
 *
 * @param {string} runId 저장된 실행 결과와 산출물 디렉터리를 찾는 실행 ID입니다.
 * @param {string} caseId 입력, 출력, 오답 산출물을 구분하는 케이스 ID입니다.
 */
async function loadWrongCase(runId, caseId) {
  const artifacts = await app.api(`/api/runs/${runId}/wrong/${caseId}`);
  state.artifacts = artifacts;
  state.selectedArtifact = "input";
  state.artifactExpanded = false;
  app.setText("wrongMeta", `${runId} · 테스트케이스 ${caseId}`);
  app.$("wrongPanel").classList.remove("hidden");
  renderArtifact();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
function currentArtifactText() {
  if (!state.artifacts) return "";
  return state.artifacts[state.selectedArtifact] || "";
}
function artifactFilename() {
  const meta = app.optional("wrongMeta")?.textContent || "wrong-case";
  const safeMeta = meta.replace(/[^\w.-]+/g, "-").replace(/^-|-$/g, "") || "wrong-case";
  return `${safeMeta}-${state.selectedArtifact}.txt`;
}

function diffLineClass(line) {
  if (line.startsWith("@@")) return "diff-hunk";
  if (line.startsWith("+++") || line.startsWith("---")) return "diff-file";
  if (line.startsWith("+")) return "diff-add";
  if (line.startsWith("-")) return "diff-remove";
  return "";
}
function renderDiffArtifact(text) {
  return text
    .split("\n")
    .map((line) => {
      const className = diffLineClass(line);
      const classAttr = className ? ` class="${className}"` : "";
      return `<span${classAttr}>${escapeHtml(line || " ")}</span>`;
    })
    .join("\n");
}
/**
 * 산출물 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderArtifact() {
  if (!state.artifacts) return;
  const key = state.selectedArtifact;
  const output = app.$("artifactOutput");
  const text = currentArtifactText();
  if (key === "diff") {
    output.innerHTML = renderDiffArtifact(text);
  } else {
    output.textContent = text;
  }
  output.classList.toggle("wrapped", Boolean(state.artifactWrap));
  const truncation = state.artifacts.truncation?.[key];
  const collapsible = Boolean(truncation?.truncated) || text.length > 1600;
  output.classList.toggle("collapsed", collapsible && !state.artifactExpanded);
  const notice = app.optional("artifactNotice");
  if (notice) {
    if (truncation?.truncated) {
      notice.textContent = `긴 데이터라 앞 ${state.artifacts.previewLimit || app.ARTIFACT_PREVIEW_LIMIT}자만 표시합니다. 생략된 문자: ${truncation.omittedChars}`;
      notice.classList.remove("hidden");
    } else {
      notice.classList.add("hidden");
      notice.textContent = "";
    }
  }
  for (const button of document.querySelectorAll(".artifact-tab")) {
    button.classList.toggle("active", button.dataset.artifact === state.selectedArtifact);
  }
  const copyButton = app.optional("artifactCopyButton");
  const downloadButton = app.optional("artifactDownloadButton");
  const wrapButton = app.optional("artifactWrapButton");
  const expandButton = app.optional("artifactExpandButton");
  if (copyButton) copyButton.disabled = !text;
  if (downloadButton) downloadButton.disabled = !text;
  if (wrapButton) {
    wrapButton.setAttribute("aria-pressed", state.artifactWrap ? "true" : "false");
    wrapButton.textContent = state.artifactWrap ? "줄 바꿈 해제" : "줄 바꿈";
  }
  if (expandButton) {
    expandButton.classList.toggle("hidden", !collapsible);
    expandButton.setAttribute("aria-pressed", state.artifactExpanded ? "true" : "false");
    expandButton.textContent = state.artifactExpanded ? "접기" : "펼치기";
  }
}
/**
 * 산출물 파일을 정책이 허용하는 대상 경로로 복사합니다.
 */
async function copyArtifact() {
  const text = currentArtifactText();
  if (!text) return;
  try {
    if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  const artifactLabels = {
    input: "입력",
    expected: "예상 출력",
    actual: "실제 출력",
    diff: "차이점",
  };
  const label = artifactLabels[state.selectedArtifact] || "산출물";
  app.showToast(`${label} 산출물을 복사했습니다.`);
}

function downloadArtifact() {
  const text = currentArtifactText();
  if (!text) return;
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = artifactFilename();
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  app.showToast(`다운로드를 준비했습니다: ${link.download}`);
}
/**
 * 산출물 wrap 표시 상태를 현재 값의 반대로 전환합니다.
 */
function toggleArtifactWrap() {
  state.artifactWrap = !state.artifactWrap;
  renderArtifact();
}
/**
 * 산출물 expanded 표시 상태를 현재 값의 반대로 전환합니다.
 */
function toggleArtifactExpanded() {
  state.artifactExpanded = !state.artifactExpanded;
  renderArtifact();
}

Object.assign(app, {
  copyArtifact,
  downloadArtifact,
  loadWrongCase,
  renderArtifact,
  renderCaseResults,
  renderLastResultAnchor,
  renderLastResultPending,
  renderLastResultUnavailable,
  recordSubmissionCooldown,
  restoreRunResult,
  resultCaseCount,
  runFormData,
  runMetricsText,
  runSubmission,
  runSummary,
  showResultModal,
  statusClassName,
  streamRun,
  submissionCooldownRemaining,
  toggleArtifactExpanded,
  toggleArtifactWrap,
});
