/**
 * 솔루션 생성, 편집, 검증, 스트레스 테스트 버튼 동작을 담당하는 브라우저 모듈입니다.
 */

import { api, normalizeErrorDetail } from "../api.js";
import { apiFilePath } from "./files.js";
import { $, escapeHtml, optional, setText } from "../dom.js";
import {
  configureSolutionArtifacts,
  openSolutionCasesModal,
} from "./solution-artifacts.js";
import {
  renderSolutionMetaForm,
  updateSolutionPreview,
  updateSolutionRenamePreview,
} from "./solution-forms.js";
import {
  getModalEditorValue,
  initializeSourceModalEditors,
  refreshModalEditor,
  setModalEditorValue,
} from "../editor/codemirror.js";
import { getEditorValue } from "../editor/core.js";
import {
  roleForFile,
  renderSolutionValidationSummary,
  renderTabFiles,
  selectSolutionPath,
  solutionParts,
} from "../resources-view.js";
import { state } from "../state.js";
import {
  dirtySolutionSet,
  failedSolutionChecks,
  formatSolutionFailureSummary,
  normalizedSolutionPath,
  solutionCheckSource,
} from "../solution-status.js";
import { appendOutput, showAlert, showResult } from "../feedback.js";
import { enqueueQueuedJob, runQueuedJob } from "../jobs-view.js";
import { showLastRun } from "../progress.js";

const solutionCallbacks = {
  closeModals: () => {},
  markFullTestDirty: () => {},
  markSolutionDirty: () => {},
  openModal: () => {},
  persistProblemLastResult: () => {},
  removeSolutionChecks: () => {},
  renderTaskPanel: () => {},
  setDirtySolutionPaths: () => {},
  streamRequest: async () => ({}),
  withErrors: async (action) => action(),
  withInlineErrors: async (action) => action(),
};
export function configureSolutionActions(callbacks = {}) {
  Object.assign(solutionCallbacks, callbacks);
  configureSolutionArtifacts({
    openModal: solutionCallbacks.openModal,
    withErrors: solutionCallbacks.withErrors,
  });
}

export { openSolutionCasesModal };
export { renderSolutionMetaForm, updateSolutionPreview, updateSolutionRenamePreview };
export function solutionFilePaths() {
  return state.files
    .filter((file) => file.path.startsWith("solutions/"))
    .map((file) => normalizedSolutionPath(file.path));
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
/**
 * 솔루션 dirty 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 *
 * @param {Array} paths 같은 작업을 적용할 파일 또는 디렉터리 경로 목록입니다.
 */
function clearSolutionDirty(paths) {
  const completed = new Set((paths || []).map(normalizedSolutionPath));
  if (!completed.size) return;
  solutionCallbacks.setDirtySolutionPaths(
    state.dirtySolutionPaths.filter((path) => !completed.has(path))
  );
}
/**
 * 솔루션 create 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 */
export function openSolutionCreateModal() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  initializeSourceModalEditors();
  $("solutionCreateName").value = "wrong_solution";
  $("solutionCreateExpected").value = "wa";
  $("solutionCreateLanguage").value = "cpp";
  setModalEditorValue("create", "");
  updateSolutionPreview();
  solutionCallbacks.openModal("solutionCreateModal");
  refreshModalEditor("create");
}
/**
 * 솔루션 edit 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 *
 * @param {string} path 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
 */
export async function openSolutionEditModal(path) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  initializeSourceModalEditors();
  const source =
    path === state.selectedFile && state.selectedTab !== "solutions"
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
  solutionCallbacks.openModal("solutionEditModal");
  refreshModalEditor("edit");
}
/**
 * 솔루션 업로드 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 */
export function openSolutionUpload() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  const input = $("solutionUploadInput");
  input.disabled = false;
  input.value = "";
  input.click();
}
export async function uploadSolutions(files) {
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
  for (const item of uploaded) solutionCallbacks.removeSolutionChecks([item.path]);
  solutionCallbacks.setDirtySolutionPaths([
    ...state.dirtySolutionPaths,
    ...uploaded.map((item) => item.path),
  ]);
  solutionCallbacks.markFullTestDirty("솔루션 업로드로 전체 테스트가 다시 필요합니다.");
  solutionCallbacks.renderTaskPanel();
  showResult(`${uploaded.length} solution file(s) uploaded.`, "summary success");
}
/**
 * 솔루션에 필요한 초기 파일과 메타데이터를 생성합니다.
 */
export async function createSolution() {
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
  solutionCallbacks.markSolutionDirty(result.created.path, "새 솔루션이 추가되어 검증이 필요합니다.");
  selectSolutionPath(result.created.path);
  solutionCallbacks.renderTaskPanel();
  solutionCallbacks.closeModals();
  showResult("새 솔루션 파일을 만들었습니다.", "summary success");
}
export async function renameSolution() {
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
  solutionCallbacks.markSolutionDirty(nextPath, "솔루션 변경으로 재검증이 필요합니다.", { oldPath });
  selectSolutionPath(nextPath);
  solutionCallbacks.renderTaskPanel();
  solutionCallbacks.closeModals();
  showResult("솔루션을 저장했습니다.", "summary success");
}
export async function verifySolutions(options = {}) {
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
  const partial = await runQueuedJob(
    `/api/problems/${state.selectedProblem}/solutions/verify/jobs`,
    {
      profile: "hidden",
      solutions: requestedPaths.length === allPaths.length ? null : requestedPaths,
    },
    { ...options, label: "솔루션 기대 결과 검증" }
  );
  clearSolutionDirty(requestedPaths);
  const result =
    requestedPaths.length === allPaths.length
      ? { ...partial, incremental: false, complete: true, totalCount: allPaths.length }
      : mergeSolutionVerification(state.lastSolutionVerification, partial);
  const currentRunPassed = Boolean(partial.passed);
  state.lastSolutionVerification = result;
  solutionCallbacks.persistProblemLastResult?.({
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
export async function verifySingleSolution(path) {
  return verifySolutions({ paths: [path], clear: false });
}

function selectedStressDuration() {
  const selected = document.querySelector("input[name='solutionStressDuration']:checked");
  return Number(selected?.value || 60);
}

function stressSolutionCheckboxes() {
  return Array.from(document.querySelectorAll("[data-stress-solution-path]"));
}

function updateStressSelectionSummary() {
  const checkboxes = stressSolutionCheckboxes();
  const selected = checkboxes.filter((input) => input.checked);
  const summary = optional("solutionStressSelectionSummary");
  if (summary) summary.textContent = `${selected.length}/${checkboxes.length}개 선택`;
  const button = optional("solutionStressStartButton");
  if (button) {
    button.disabled = !selected.length;
    button.title = selected.length ? "" : "Stress 테스트할 솔루션을 하나 이상 선택하세요.";
  }
}
function selectedSolutionPathForStress() {
  const path = normalizedSolutionPath(state.selectedFile);
  return path?.startsWith("solutions/") ? path : "";
}

function applyStressSolutionScope(scope = $("solutionStressScope").value) {
  const checkboxes = stressSolutionCheckboxes();
  const selectedPath = selectedSolutionPathForStress();
  if (scope === "all") {
    for (const input of checkboxes) input.checked = true;
  } else if (scope === "selected" && selectedPath) {
    for (const input of checkboxes) {
      input.checked = normalizedSolutionPath(input.value) === selectedPath;
    }
  }
  updateStressSelectionSummary();
}
/**
 * 솔루션 스트레스 테스트 scope 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
export function updateSolutionStressScope() {
  applyStressSolutionScope();
}
function renderStressSolutionSelection() {
  const container = optional("solutionStressSelection");
  if (!container) return;
  const paths = solutionFilePaths();
  const selectedPath = selectedSolutionPathForStress();
  if (!paths.length) {
    container.innerHTML = escapeHtml("") + `<div class="stress-solution-empty">솔루션 파일이 없습니다.</div>`;
    updateStressSelectionSummary();
    return;
  }
  container.innerHTML = escapeHtml("") + paths
    .map((path) => {
      const isCurrent = normalizedSolutionPath(path) === selectedPath;
      return `
        <label class="stress-solution-option">
          <input type="checkbox" data-stress-solution-path value="${escapeHtml(path)}" />
          <span>
            <strong>${escapeHtml(path)}</strong>
            <small>${escapeHtml(roleForFile(path))}${isCurrent ? " · 현재 선택" : ""}</small>
          </span>
        </label>
      `;
    })
    .join("");
  for (const input of stressSolutionCheckboxes()) {
    input.addEventListener("change", () => {
      $("solutionStressScope").value = "custom";
      updateStressSelectionSummary();
    });
  }
}

function selectedStressSolutions() {
  const selected = stressSolutionCheckboxes()
    .filter((input) => input.checked)
    .map((input) => normalizedSolutionPath(input.value));
  if (!selected.length) throw new Error("Stress 테스트할 솔루션을 하나 이상 선택하세요.");
  const allPaths = solutionFilePaths();
  if (selected.length === allPaths.length) return null;
  return selected;
}
function stressProfileValue() {
  return $("solutionStressProfile").value.trim() || state.detail?.metadata?.defaultProfile || "hidden";
}

function stressMaxCasesValue() {
  const value = $("solutionStressMaxCases").value.trim();
  if (!value) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.floor(numeric) : null;
}
/**
 * 솔루션 스트레스 테스트 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 */
export function openSolutionStressModal() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  $("solutionStressProfile").value = state.lastSolutionStress?.profile
    || state.detail?.metadata?.defaultProfile
    || "hidden";
  $("solutionStressStopOnMismatch").checked = true;
  $("solutionStressMaxCases").value = "";
  const selectedOption = $("solutionStressScope").querySelector("option[value='selected']");
  const hasSelectedSolution = Boolean(selectedSolutionPathForStress());
  if (selectedOption) selectedOption.disabled = !hasSelectedSolution;
  renderStressSolutionSelection();
  $("solutionStressScope").value = hasSelectedSolution ? "selected" : "all";
  applyStressSolutionScope($("solutionStressScope").value);
  solutionCallbacks.openModal("solutionStressModal");
}
export async function runSolutionStress(options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  const profile = options.profile || stressProfileValue();
  const solutions = options.solutions === undefined ? selectedStressSolutions() : options.solutions;
  const body = {
    profile,
    duration_seconds: options.durationSeconds || selectedStressDuration(),
    max_cases: options.maxCases === undefined ? stressMaxCasesValue() : options.maxCases,
    solutions,
    stop_on_first_mismatch:
      options.stopOnFirstMismatch === undefined
        ? $("solutionStressStopOnMismatch").checked
        : options.stopOnFirstMismatch,
  };
  const finishStressRun = (result) => {
    state.lastSolutionStress = result;
    renderSolutionValidationSummary();
    renderTabFiles();
    appendOutput(JSON.stringify(result, null, 2));
    const summary = result.passed
      ? `${result.iterations || 0}회 stress에서 mismatch를 찾지 못했습니다.`
      : `${result.mismatchCount || 0}개 mismatch를 찾았습니다.`;
    showLastRun(
      result.passed ? "Stress 테스트 완료" : "Stress mismatch 확인 필요",
      summary,
      result.passed ? "success" : "error"
    );
    if (result.passed) {
      showResult("Stress test passed.", "summary success");
    } else {
      showAlert("Stress mismatch를 찾았습니다. 솔루션 탭에서 preview 후 데이터로 추가할 수 있습니다.", "error", {
        title: "Stress mismatch",
        timeout: 5000,
      });
    }
  };
  const job = await enqueueQueuedJob(
    `/api/problems/${encodeURIComponent(state.selectedProblem)}/solutions/stress/jobs`,
    body,
    {
      label: "Stress 테스트",
      onResult: finishStressRun,
      onFailure: (error) => {
        showAlert(error.message, "error", {
          title: "Stress 테스트 실패",
          timeout: 7000,
        });
      },
    }
  );
  solutionCallbacks.closeModals();
  showAlert("Stress 테스트가 백그라운드에서 실행 중입니다. 작업 센터에서 반복 수와 seed를 확인할 수 있습니다.", "info", {
    title: "Stress 실행 중",
    timeout: 4500,
  });
  return job;
}
function stressMismatchByKey(caseId, solutionKey) {
  const result = state.lastSolutionStress;
  return (result?.mismatches || []).find(
    (item) => item.caseId === caseId && item.solutionKey === solutionKey
  );
}
function stressArtifactText() {
  const artifact = state.stressMismatchPreview;
  if (!artifact) return "";
  return artifact[state.selectedStressArtifact] || "";
}
function renderStressDiff(text) {
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

function defaultStressCaseName(artifact, mode) {
  const metadata = artifact?.metadata || {};
  const source = String(metadata.generatorCaseName || metadata.caseName || metadata.caseId || "stress");
  return `${source}-${metadata.caseId || artifact?.caseId || "case"}-${mode}`.replace(/[^A-Za-z0-9_.-]+/g, "-");
}
function stressReviewBody(artifact) {
  const metadata = artifact?.metadata || {};
  const selected = state.selectedStressArtifact || "input";
  const text = stressArtifactText();
  const truncation = artifact?.truncation?.[selected];
  const body = selected === "diff" ? renderStressDiff(text) : escapeHtml(text);
  const mode = state.pendingStressAppend?.mode || "fixed";
  const profile = state.pendingStressAppend?.profile || artifact?.metadata?.profile || state.lastSolutionStress?.profile || "hidden";
  const caseName = state.pendingStressAppend?.name || defaultStressCaseName(artifact, mode);
  return `
    <div class="stress-review-summary">
      <span><small>solution</small><strong>${escapeHtml(metadata.solution || "-")}</strong></span>
      <span><small>status</small><strong>${escapeHtml(metadata.expectedStatus || "-")} → ${escapeHtml(metadata.actualStatus || "-")}</strong></span>
      <span><small>seed</small><strong>${escapeHtml(metadata.seed ?? "-")}</strong></span>
      <span><small>generator</small><strong>${escapeHtml(metadata.generatorCaseName || "-")}</strong></span>
    </div>
    ${metadata.message ? `<div class="solution-cases-message">${escapeHtml(normalizeErrorDetail(metadata.message))}</div>` : ""}
    <div class="solution-artifact-preview">
      <div class="solution-artifact-heading">
        <div>
          <strong>${escapeHtml(artifact.stressRunId || "")} · ${escapeHtml(artifact.caseId || "")}</strong>
          <span>${escapeHtml(selected)}</span>
        </div>
        <button type="button" data-stress-artifact-copy>Copy</button>
      </div>
      <div class="solution-artifact-tabs">
        ${["input", "expected", "actual", "diff"]
          .map(
            (name) =>
              `<button type="button" class="${name === selected ? "active" : ""}" data-stress-artifact-tab="${name}">${name}</button>`
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
      <pre class="solution-artifact-output ${selected === "diff" ? "diff" : ""}">${body}</pre>
    </div>
    <div class="stress-append-panel">
      <label>
        Profile
        <input id="stressAppendProfile" value="${escapeHtml(profile)}" />
      </label>
      <label>
        Mode
        <select id="stressAppendMode">
          <option value="fixed" ${mode === "fixed" ? "selected" : ""}>Fixed</option>
          <option value="generator" ${mode === "generator" ? "selected" : ""}>Generator</option>
        </select>
      </label>
      <label>
        Case name
        <input id="stressAppendName" value="${escapeHtml(caseName)}" />
      </label>
      <button id="stressAppendButton" class="primary" type="button">데이터로 추가</button>
      <button id="stressRerunButton" type="button">다시 Stress</button>
    </div>
  `;
}
/**
 * 스트레스 테스트 review 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderStressReview() {
  const artifact = state.stressMismatchPreview;
  if (!artifact) return;
  setText("solutionStressReviewTitle", `${artifact.caseId} · ${artifact.metadata?.solution || ""}`);
  $("solutionStressReviewBody").innerHTML = escapeHtml("") + stressReviewBody(artifact);
  for (const button of document.querySelectorAll("[data-stress-artifact-tab]")) {
    button.addEventListener("click", () => {
      state.selectedStressArtifact = button.dataset.stressArtifactTab || "input";
      renderStressReview();
    });
  }
  optional("stressAppendMode")?.addEventListener("change", () => {
    state.pendingStressAppend = {
      ...(state.pendingStressAppend || {}),
      mode: $("stressAppendMode").value,
      name: defaultStressCaseName(artifact, $("stressAppendMode").value),
    };
    renderStressReview();
  });
  optional("stressAppendProfile")?.addEventListener("input", () => {
    state.pendingStressAppend = {
      ...(state.pendingStressAppend || {}),
      profile: $("stressAppendProfile").value,
    };
  });
  optional("stressAppendName")?.addEventListener("input", () => {
    state.pendingStressAppend = {
      ...(state.pendingStressAppend || {}),
      name: $("stressAppendName").value,
    };
  });
  optional("stressAppendButton")?.addEventListener("click", () => {
    void solutionCallbacks.withErrors(appendStressMismatch, "Stress 데이터를 추가하는 중입니다.");
  });
  optional("stressRerunButton")?.addEventListener("click", () => {
    void solutionCallbacks.withInlineErrors(() => runSolutionStress({
      profile: $("stressAppendProfile").value.trim() || state.lastSolutionStress?.profile || "hidden",
      solutions: state.lastSolutionStress?.checkedSolutions?.map((item) => item.solution) || null,
      durationSeconds: state.lastSolutionStress?.durationSeconds || 60,
      stopOnFirstMismatch: true,
    }), "Stress 테스트를 다시 실행하는 중입니다.");
  });
  document.querySelector("[data-stress-artifact-copy]")?.addEventListener("click", () => {
    void copyStressArtifact();
  });
}
/**
 * 스트레스 테스트 산출물 파일을 정책이 허용하는 대상 경로로 복사합니다.
 */
async function copyStressArtifact() {
  const text = stressArtifactText();
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
 * 스트레스 테스트 mismatch 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 *
 * @param {string} caseId 입력, 출력, 오답 산출물을 구분하는 케이스 ID입니다.
 * @param {any} solutionKey 스트레스 테스트 mismatch 모달을 계산하거나 검증할 때 필요한 솔루션 key 입력입니다.
 * @param {string} mode 스트레스 테스트 mismatch 모달을 계산하거나 검증할 때 필요한 mode 입력입니다.
 */
export async function openStressMismatchModal(caseId, solutionKey, mode = null) {
  if (!state.selectedProblem || !state.lastSolutionStress?.stressRunId) {
    throw new Error("Stress 결과가 없습니다.");
  }
  const mismatch = stressMismatchByKey(caseId, solutionKey);
  const artifact = await api(
    `/api/problems/${encodeURIComponent(state.selectedProblem)}/solutions/stress/runs/${encodeURIComponent(state.lastSolutionStress.stressRunId)}/mismatches/${encodeURIComponent(caseId)}/${encodeURIComponent(solutionKey)}`
  );
  state.stressMismatchPreview = artifact;
  state.selectedStressArtifact = "input";
  state.pendingStressAppend = {
    mode: mode || "fixed",
    profile: state.lastSolutionStress.profile || "hidden",
    name: defaultStressCaseName({ ...artifact, metadata: mismatch || artifact.metadata }, mode || "fixed"),
  };
  renderStressReview();
  solutionCallbacks.openModal("solutionStressReviewModal");
}
export async function appendStressMismatch() {
  const artifact = state.stressMismatchPreview;
  if (!state.selectedProblem || !artifact) throw new Error("추가할 Stress mismatch가 없습니다.");
  const body = {
    profile: $("stressAppendProfile").value.trim() || state.lastSolutionStress?.profile || "hidden",
    mode: $("stressAppendMode").value || "fixed",
    name: $("stressAppendName").value.trim(),
  };
  const result = await api(
    `/api/problems/${encodeURIComponent(state.selectedProblem)}/solutions/stress/runs/${encodeURIComponent(artifact.stressRunId)}/mismatches/${encodeURIComponent(artifact.caseId)}/${encodeURIComponent(artifact.solutionKey)}/append`,
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );
  state.files = result.files || state.files;
  solutionCallbacks.setDirtySolutionPaths(solutionFilePaths());
  solutionCallbacks.markFullTestDirty("Stress 데이터 추가로 전체 테스트가 다시 필요합니다.");
  renderTabFiles();
  renderSolutionValidationSummary();
  showResult(`cases.yml OK · ${result.caseName} 추가`, "summary success");
  showAlert(`${result.caseName} 케이스를 ${result.profile} profile에 추가했습니다.`, "success", {
    title: "데이터 추가 완료",
    timeout: 4500,
  });
  return result;
}
