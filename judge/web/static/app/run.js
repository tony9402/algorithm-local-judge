const app = window.AljApp;
const { state } = app;

/**
 * runFormData 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function runFormData() {
  const formData = new FormData();
  formData.append("problem_id", app.$("problemSelect").value);
  formData.append("profile", app.judgeProfile());
  formData.append("source_mode", state.sourceMode);
  if (state.sourceMode === "upload") {
    const file = app.$("sourceFileInput").files[0];
    if (!file) throw new Error("Source file upload is required.");
    formData.append("file", file);
  } else {
    formData.append("filename", app.$("filenameInput").value.trim() || app.$("languageHint").value);
    formData.append("source_text", app.$("sourceTextInput").value);
  }
  return formData;
}

/**
 * streamRun 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} formData `formData` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function streamRun(formData) {
  return app.runQueuedJob("/api/run/jobs", {
    method: "POST",
    body: formData,
  });
}

/**
 * resultCaseCount 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} result `result` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function resultCaseCount(result) {
  if (Number.isFinite(result.caseCount)) return result.caseCount;
  return result.cases?.length || 0;
}

/**
 * restoreRunResult 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} result `result` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function restoreRunResult(result) {
  state.artifacts = null;
  app.$("wrongPanel").classList.add("hidden");
  app.hideGenerationProgress();
  app.setBadge(result.status.replaceAll("_", " "), statusClassName(result.status));
  app.setText("resultMeta", `${result.problemId} · ${result.profile} · ${result.language} · ${result.runId}`);
  app.setStatusCard("data", "Ready", result.profile);
  app.setStatusCard(
    "judge",
    result.status.replaceAll("_", " "),
    app.profileCaseText(resultCaseCount(result), result.profile)
  );
  app.setStatusCard("run", result.runId, runMetricsText(result));
  app.setSummary(
    runSummary(result),
    result.status === "accepted" ? "result-summary success" : "result-summary error"
  );
  if (result.firstFailedCase) {
    await loadWrongCase(result.runId, result.firstFailedCase);
  }
}

/**
 * runSubmission 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
async function runSubmission() {
  state.artifacts = null;
  app.$("wrongPanel").classList.add("hidden");
  app.clearDebugLog();
  app.setBadge("Running", "neutral");
  app.setStatusCard("data", "Checking", app.judgeProfile());
  app.setStatusCard("judge", "Waiting");
  app.setStatusCard("run", "-", "In progress");
  app.setSummary(`Judging submission with ${app.judgeProfile()} cases.`, "result-summary");
  const compileResult = await app.compileCasesData({ showSuccess: false });
  if (!compileResult.valid) return;
  const totalCases = app.compiledCaseCount(compileResult);
  app.setGenerationProgress(0, totalCases, "Data generation");
  app.appendRunLog("Starting judge run.");
  const result = await streamRun(runFormData());
  if (!result) throw new Error("Run finished without a result.");
  app.setBadge(result.status.replaceAll("_", " "), statusClassName(result.status));
  app.setText("resultMeta", `${result.problemId} · ${result.profile} · ${result.language} · ${result.runId}`);
  app.setStatusCard("data", "Ready", result.profile);
  app.setStatusCard(
    "judge",
    result.status.replaceAll("_", " "),
    app.profileCaseText(resultCaseCount(result), result.profile)
  );
  app.setStatusCard("run", result.runId, runMetricsText(result));
  app.setSummary(runSummary(result), result.status === "accepted" ? "result-summary success" : "result-summary error");
  if (result.message) state.debugLogs.push(result.message);
  app.renderDebugLog();
  if (result.firstFailedCase) {
    await loadWrongCase(result.runId, result.firstFailedCase);
  }
  await app.refreshSecondaryData();
}

/**
 * statusClassName 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} status `status` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function statusClassName(status) {
  if (status === "accepted") return "accepted";
  if (status === "wrong_answer") return "wrong";
  if (status === "compile_error") return "compile";
  if (status === "runtime_error") return "runtime";
  if (status === "time_limit") return "time";
  if (status === "memory_limit") return "memory";
  return "neutral";
}

/**
 * runSummary 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} result `result` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function runSummary(result) {
  const metrics = runMetricsText(result);
  if (result.status === "accepted") {
    return `Accepted after ${app.profileCaseText(resultCaseCount(result), result.profile)}. ${metrics}`;
  }
  const failed = result.firstFailedCase ? ` on case ${result.firstFailedCase}` : "";
  return `${result.status.replaceAll("_", " ")}${failed}. ${metrics}`;
}

/**
 * runMetricsText 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} result `result` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function runMetricsText(result) {
  const metrics = result.metrics || {};
  const time = metrics.maxTimeLabel || "unavailable";
  const memory = metrics.maxMemoryLabel || "unavailable";
  return `max time ${time} · max memory ${memory}`;
}

/**
 * loadWrongCase 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} runId `runId` 값입니다.
 * @param {any} caseId `caseId` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function loadWrongCase(runId, caseId) {
  const artifacts = await app.api(`/api/runs/${runId}/wrong/${caseId}`);
  state.artifacts = artifacts;
  state.selectedArtifact = "input";
  state.artifactExpanded = false;
  app.setText("wrongMeta", `${runId} · case ${caseId}`);
  app.$("wrongPanel").classList.remove("hidden");
  renderArtifact();
}

/**
 * escapeHtml 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/**
 * currentArtifactText 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function currentArtifactText() {
  if (!state.artifacts) return "";
  return state.artifacts[state.selectedArtifact] || "";
}

/**
 * artifactFilename 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function artifactFilename() {
  const meta = app.optional("wrongMeta")?.textContent || "wrong-case";
  const safeMeta = meta.replace(/[^\w.-]+/g, "-").replace(/^-|-$/g, "") || "wrong-case";
  return `${safeMeta}-${state.selectedArtifact}.txt`;
}

/**
 * diffLineClass 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} line `line` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function diffLineClass(line) {
  if (line.startsWith("@@")) return "diff-hunk";
  if (line.startsWith("+++") || line.startsWith("---")) return "diff-file";
  if (line.startsWith("+")) return "diff-add";
  if (line.startsWith("-")) return "diff-remove";
  return "";
}

/**
 * renderDiffArtifact 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} text `text` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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
 * renderArtifact 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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
    wrapButton.textContent = state.artifactWrap ? "No wrap" : "Wrap";
  }
  if (expandButton) {
    expandButton.classList.toggle("hidden", !collapsible);
    expandButton.setAttribute("aria-pressed", state.artifactExpanded ? "true" : "false");
    expandButton.textContent = state.artifactExpanded ? "Collapse" : "Expand";
  }
}

/**
 * copyArtifact 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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
  app.showToast(`Copied ${state.selectedArtifact} artifact.`);
}

/**
 * downloadArtifact 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
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
  app.showToast(`Download prepared: ${link.download}`);
}

/**
 * toggleArtifactWrap 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function toggleArtifactWrap() {
  state.artifactWrap = !state.artifactWrap;
  renderArtifact();
}

/**
 * toggleArtifactExpanded 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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
  restoreRunResult,
  resultCaseCount,
  runFormData,
  runMetricsText,
  runSubmission,
  runSummary,
  statusClassName,
  streamRun,
  toggleArtifactExpanded,
  toggleArtifactWrap,
});
