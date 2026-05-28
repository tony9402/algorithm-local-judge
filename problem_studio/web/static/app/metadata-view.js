import { $, escapeHtml, optional, setText } from "./dom.js";
import {
  METADATA_TIMEOUT_FIELDS,
  METADATA_TOOL_FIELDS,
  SAFE_PROBLEM_ID,
  state,
} from "./state.js";

const metadataCallbacks = {
  /**
   * folderLabel 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} folder `folder` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  folderLabel: (folder) => String(folder || "").trim() || "기본",
  /**
   * hasUnsavedChanges 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  hasUnsavedChanges: () => false,
  /**
   * markFullTestDirty 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  markFullTestDirty: () => {},
  /**
   * renderProblems 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renderProblems: () => {},
  /**
   * syncWorkspaceProblemSummaries 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  syncWorkspaceProblemSummaries: () => {},
  /**
   * updateMobileHeader 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateMobileHeader: () => {},
};

/**
 * configureMetadataView 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureMetadataView(callbacks = {}) {
  Object.assign(metadataCallbacks, callbacks);
}

/**
 * positiveIntegerInput 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @param {any} fallback `fallback` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function positiveIntegerInput(id, fallback) {
  const value = Number.parseInt($(id).value, 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

/**
 * textInputValue 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @param {any} fallback `fallback` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function textInputValue(id, fallback = "") {
  return $(id).value.trim() || fallback;
}

/**
 * safeMetadataPath 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function safeMetadataPath(value) {
  const path = String(value || "").trim();
  return path && !path.startsWith("/") && !path.split("/").includes("..");
}

/**
 * metadataFormIssues 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function metadataFormIssues() {
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

/**
 * renderMetadataValidation 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function renderMetadataValidation() {
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

/**
 * metadataRawEditorDirty 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function metadataRawEditorDirty() {
  return state.selectedFile === "problem.json" && metadataCallbacks.hasUnsavedChanges();
}

/**
 * currentMetadataDraft 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function currentMetadataDraft() {
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

/**
 * currentProblemIdDraft 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function currentProblemIdDraft() {
  return textInputValue("metadataProblemIdInput", state.selectedProblem || "");
}

/**
 * applyProblemMetadataToUi 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} metadata `metadata` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function applyProblemMetadataToUi(metadata, options = {}) {
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
  const meta = `폴더 ${metadataCallbacks.folderLabel(metadata.folder)} · 버전 ${
    metadata.version ?? "-"
  } · 기본 프로필 ${metadata.defaultProfile || "-"}`;
  setText("problemTitle", title);
  setText("problemMeta", meta);
  metadataCallbacks.updateMobileHeader(
    title,
    `${metadataCallbacks.folderLabel(metadata.folder)} · v${metadata.version ?? "-"} · ${
      metadata.defaultProfile || "-"
    }`
  );
  metadataCallbacks.syncWorkspaceProblemSummaries();
  metadataCallbacks.renderProblems(state.problems);
  if (options.markDirty) {
    metadataCallbacks.markFullTestDirty("문제 메타데이터가 변경되어 전체 테스트가 다시 필요합니다.");
  }
}

/**
 * updateMetadataPreview 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function updateMetadataPreview() {
  if (state.selectedTab !== "info" || !state.selectedProblem) return;
  const metadata = currentMetadataDraft();
  const title = `${state.selectedProblem} ${metadata.title || ""}`.trim();
  const meta = `폴더 ${metadataCallbacks.folderLabel(metadata.folder)} · 버전 ${
    metadata.version ?? "-"
  } · 기본 프로필 ${metadata.defaultProfile || "-"}`;
  setText("problemTitle", title);
  setText("problemMeta", meta);
  metadataCallbacks.updateMobileHeader(
    title,
    `${metadataCallbacks.folderLabel(metadata.folder)} · v${metadata.version ?? "-"} · ${
      metadata.defaultProfile || "-"
    }`
  );
  renderMetadataValidation();
}

/**
 * populateMetadataForm 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} metadata `metadata` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function populateMetadataForm(metadata) {
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
