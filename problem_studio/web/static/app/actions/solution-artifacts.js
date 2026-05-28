import { api, normalizeErrorDetail } from "../api.js";
import { $, escapeHtml, setText } from "../dom.js";
import { showAlert } from "../feedback.js";
import { roleForFile } from "../resources-view.js";
import { state } from "../state.js";
import {
  formatDurationMs,
  formatMemoryBytes,
  solutionCaseMemory,
  solutionCaseName,
  solutionCaseStatus,
  solutionCaseTime,
  solutionCheckCases,
  solutionCheckForPath,
  solutionCheckMetrics,
  statusLabelForResult,
  statusToneForResult,
} from "../solution-status.js";

const artifactCallbacks = {
  /**
   * openModal 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  openModal: () => {},
  /**
   * withErrors 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} action `action` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  withErrors: async (action) => action(),
};

/**
 * configureSolutionArtifacts 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureSolutionArtifacts(callbacks = {}) {
  Object.assign(artifactCallbacks, callbacks);
}

/**
 * isFailedSolutionCase 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} status `status` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function isFailedSolutionCase(status) {
  return status !== "ok" && status !== "accepted";
}

/**
 * escapeAttribute 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("'", "&#39;");
}

/**
 * renderSolutionCaseRows 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} check `check` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function renderSolutionCaseRows(check) {
  const cases = solutionCheckCases(check);
  if (!cases.length) return "";
  const rows = cases
    .map((item) => {
      const status = solutionCaseStatus(item);
      const caseName = solutionCaseName(item);
      const canPreview = check.runId && isFailedSolutionCase(status);
      return `
        <div class="solution-case-row ${statusToneForResult(status)}">
          <span class="solution-case-name" title="${escapeHtml(caseName)}">
            ${escapeHtml(caseName)}
          </span>
          <strong>${escapeHtml(status === "ok" ? "OK" : statusLabelForResult(status))}</strong>
          <span>${escapeHtml(formatDurationMs(solutionCaseTime(item)))}</span>
          <span>${escapeHtml(formatMemoryBytes(solutionCaseMemory(item)))}</span>
          <span>
            ${
              canPreview
                ? `<button type="button" data-solution-artifact-case="${escapeAttribute(caseName)}">Preview</button>`
                : "-"
            }
          </span>
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
        <span>Preview</span>
      </div>
      ${rows}
    </div>
  `;
}

/**
 * solutionArtifactText 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function solutionArtifactText() {
  const artifact = state.solutionArtifactPreview;
  if (!artifact) return "";
  return artifact[state.selectedSolutionArtifact] || "";
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
      let className = "";
      if (line.startsWith("@@")) className = "diff-hunk";
      else if (line.startsWith("+++") || line.startsWith("---")) className = "diff-file";
      else if (line.startsWith("+")) className = "diff-add";
      else if (line.startsWith("-")) className = "diff-remove";
      const classAttr = className ? ` class="${className}"` : "";
      return `<span${classAttr}>${escapeHtml(line || " ")}</span>`;
    })
    .join("\n");
}

/**
 * wireSolutionArtifactPreview 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function wireSolutionArtifactPreview() {
  for (const button of document.querySelectorAll("[data-solution-artifact-tab]")) {
    button.addEventListener("click", () => {
      state.selectedSolutionArtifact = button.dataset.solutionArtifactTab || "input";
      renderSolutionArtifactPreview();
    });
  }
  const copyButton = document.querySelector("[data-solution-artifact-copy]");
  copyButton?.addEventListener("click", () => {
    void copySolutionArtifactPreview();
  });
}

/**
 * renderSolutionArtifactPreview 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function renderSolutionArtifactPreview() {
  const panel = document.getElementById("solutionArtifactPreview");
  if (!panel) return;
  const artifact = state.solutionArtifactPreview;
  if (!artifact) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  const key = state.selectedSolutionArtifact || "input";
  const text = solutionArtifactText();
  const truncation = artifact.truncation?.[key];
  const body = key === "diff" ? renderDiffArtifact(text) : escapeHtml(text);
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div class="solution-artifact-heading">
      <div>
        <strong>${escapeHtml(artifact.runId || "")} · ${escapeHtml(artifact.caseId || "")}</strong>
        <span>${escapeHtml(key)}</span>
      </div>
      <button type="button" data-solution-artifact-copy>Copy</button>
    </div>
    <div class="solution-artifact-tabs">
      ${["input", "expected", "actual", "diff"]
        .map(
          (name) =>
            `<button type="button" class="${name === key ? "active" : ""}" data-solution-artifact-tab="${name}">${name}</button>`
        )
        .join("")}
    </div>
    ${
      truncation?.truncated
        ? `<div class="solution-artifact-notice">긴 데이터라 앞 ${escapeHtml(
            artifact.previewLimit || 12000
          )}자만 표시합니다. 생략된 문자: ${escapeHtml(truncation.omittedChars)}</div>`
        : ""
    }
    <pre class="solution-artifact-output ${key === "diff" ? "diff" : ""}">${body}</pre>
  `;
  wireSolutionArtifactPreview();
}

/**
 * copySolutionArtifactPreview 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
async function copySolutionArtifactPreview() {
  const text = solutionArtifactText();
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
  showAlert("Artifact copied.", "success", { title: "Copied", timeout: 2500 });
}

/**
 * loadSolutionArtifactPreview 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} check `check` 값입니다.
 * @param {any} caseId `caseId` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function loadSolutionArtifactPreview(check, caseId) {
  if (!state.selectedProblem || !check.runId) return;
  const artifact = await api(
    `/api/problems/${encodeURIComponent(state.selectedProblem)}/solutions/runs/${encodeURIComponent(check.runId)}/wrong/${encodeURIComponent(caseId)}`
  );
  state.solutionArtifactPreview = {
    ...artifact,
    runId: check.runId,
    caseId,
  };
  state.selectedSolutionArtifact = "input";
  renderSolutionArtifactPreview();
}

/**
 * renderSolutionCasesBody 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} check `check` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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
    <div id="solutionArtifactPreview" class="solution-artifact-preview hidden"></div>
  `;
}

/**
 * openSolutionCasesModal 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function openSolutionCasesModal(path) {
  const check = solutionCheckForPath(path);
  if (!check) {
    throw new Error("아직 표시할 채점 결과가 없습니다. 개별 테스트나 기대 결과 검증을 먼저 실행하세요.");
  }
  setText("solutionCasesTitle", path);
  setText("solutionCasesSubtitle", `${roleForFile(path)} · ${statusLabelForResult(check.expectedStatus)} 기대`);
  state.solutionArtifactPreview = null;
  state.selectedSolutionArtifact = "input";
  $("solutionCasesBody").innerHTML = renderSolutionCasesBody(check);
  for (const button of document.querySelectorAll("[data-solution-artifact-case]")) {
    button.addEventListener("click", () => {
      void artifactCallbacks.withErrors(() =>
        loadSolutionArtifactPreview(check, button.dataset.solutionArtifactCase)
      );
    });
  }
  artifactCallbacks.openModal("solutionCasesModal");
}
