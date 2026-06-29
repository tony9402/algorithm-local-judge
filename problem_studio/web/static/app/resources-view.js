/**
 * 리소스 화면 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { normalizeErrorDetail } from "./api.js";
import { $, escapeHtml, optional } from "./dom.js";
import {
  EXPECTED_STATUS_BY_TOKEN,
  FILE_ROLES,
  LANGUAGE_BY_EXTENSION,
  TAB_CONFIGS,
  state,
} from "./state.js";
import {
  dirtySolutionSet,
  formatDurationMs,
  formatMemoryBytes,
  normalizedSolutionPath,
  solutionCheckForPath,
  solutionCheckMetrics,
  solutionValidationStatusForFile,
  statusLabelForResult,
} from "./solution-status.js";
import { rememberView, selectionKey } from "./view-persistence.js";

const resourceCallbacks = {
  deleteSolution: async () => {},
  openFile: async () => {},
  openSolutionStressModal: () => {},
  openStressMismatchModal: async () => {},
  openSolutionCasesModal: async () => {},
  openSolutionEditModal: async () => {},
  validationStatusForFile: () => null,
  verifySingleSolution: async () => {},
  withErrors: async (action) => action(),
};
export function configureResourcesView(callbacks = {}) {
  Object.assign(resourceCallbacks, callbacks);
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("'", "&#39;");
}
export function filesForTab(tabId = state.selectedTab) {
  if (!state.detail) return [];
  if (tabId === "solutions") {
    return state.files.filter((file) => file.path.startsWith("solutions/"));
  }
  const paths = TAB_CONFIGS[tabId].files || [];
  return paths
    .map((path) => state.files.find((file) => file.path === path) || { path, size: 0 })
    .filter(Boolean);
}
export function solutionParts(path) {
  const filename = (path || "").split("/").pop() || "";
  const pypyMatch = filename.match(/^(.*)\.pypy\.(ac|wa|tle|mle)\.py$/);
  if (pypyMatch) {
    return {
      name: pypyMatch[1],
      expected: pypyMatch[2],
      language: "pypy",
    };
  }
  const match = filename.match(/^(.*)\.(ac|wa|tle|mle)(\.[^.]+)$/);
  const extension = match ? match[3] : filename.match(/\.[^.]+$/)?.[0] || ".cpp";
  return {
    name: match ? match[1] : filename.replace(/\.[^.]+$/, ""),
    expected: match ? match[2] : "wa",
    language: LANGUAGE_BY_EXTENSION[extension.toLowerCase()] || "cpp",
  };
}
export function roleForFile(path) {
  if (path && path === state.detail?.metadata?.tools?.solution) return "기준 정답";
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
export function solutionExpectedStatusFromPath(path) {
  const parts = solutionParts(path);
  return EXPECTED_STATUS_BY_TOKEN[parts.expected] || "unknown";
}
export function isReferenceSolutionPath(path) {
  return Boolean(path && path === state.detail?.metadata?.tools?.solution);
}

function solutionRowFacts(file) {
  const check = solutionCheckForPath(file.path);
  const metrics = solutionCheckMetrics(check);
  const expectedStatus = check?.expectedStatus || solutionExpectedStatusFromPath(file.path);
  const actualStatus = check?.actualStatus || "";
  const dirty = dirtySolutionSet().has(normalizedSolutionPath(file.path));
  const status = solutionValidationStatusForFile(file.path);
  const active = ["verifying", "test-running"].includes(status?.className);
  return {
    check,
    metrics,
    dirty,
    status,
    expected: statusLabelForResult(expectedStatus),
    actual: active ? status.label : dirty ? "재검증" : actualStatus ? statusLabelForResult(actualStatus) : "대기",
    runId: check?.runId || "-",
    message: normalizeErrorDetail(check?.message) || "",
  };
}
/**
 * 솔루션 리소스 item 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {any} list 솔루션 리소스 item을 계산하거나 검증할 때 필요한 목록 입력입니다.
 * @param {any} file 업로드 요청에서 받은 파일 스트림 객체입니다.
 */
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
      <button class="danger" type="button" data-solution-delete="${escapeHtml(file.path)}">삭제</button>
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
    void resourceCallbacks.withErrors(
      () => resourceCallbacks.verifySingleSolution(file.path),
      "솔루션 하나를 테스트하는 중입니다."
    );
  });
  item.querySelector("[data-solution-cases]")?.addEventListener("click", (event) => {
    event.stopPropagation();
    void resourceCallbacks.withErrors(
      () => resourceCallbacks.openSolutionCasesModal(file.path),
      "채점 결과를 여는 중입니다."
    );
  });
  item.querySelector("[data-solution-edit]")?.addEventListener("click", (event) => {
    event.stopPropagation();
    void resourceCallbacks.withErrors(
      () => resourceCallbacks.openSolutionEditModal(file.path),
      "솔루션 편집창을 여는 중입니다."
    );
  });
  item.querySelector("[data-solution-delete]")?.addEventListener("click", (event) => {
    event.stopPropagation();
    void resourceCallbacks.withErrors(
      () => resourceCallbacks.deleteSolution(file.path),
      "솔루션을 삭제하는 중입니다."
    );
  });
  list.appendChild(item);
}
export function renderTabFiles() {
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
  const matchCount = visibleFiles.filter((file) =>
    resourceCallbacks.validationStatusForFile(file.path)?.className === "match"
  ).length;
  const mismatchCount = visibleFiles.filter((file) =>
    resourceCallbacks.validationStatusForFile(file.path)?.className === "mismatch"
  ).length;
  const staleCount = visibleFiles.filter((file) =>
    resourceCallbacks.validationStatusForFile(file.path)?.className === "stale"
  ).length;
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
    const validationStatus = resourceCallbacks.validationStatusForFile(file.path);
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
      void resourceCallbacks.withErrors(
        () => resourceCallbacks.openFile(file.path),
        "파일을 불러오는 중입니다."
      );
    });
    list.appendChild(item);
  }
}
/**
 * 솔루션 검증 summary 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
export function renderSolutionValidationSummary() {
  const panel = optional("solutionValidationSummary");
  if (!panel) return;
  panel.className = "solution-validation-summary hidden";
  panel.innerHTML = "";
  if (state.selectedTab !== "solutions" || !state.lastSolutionStress) return;
  const result = state.lastSolutionStress;
  const mismatches = result.mismatches || [];
  panel.className = `solution-validation-summary ${result.passed ? "success" : "error"}`;
  const duration = result.elapsedSeconds ? `${Number(result.elapsedSeconds).toFixed(1)}s` : "-";
  panel.innerHTML = `
    <div class="solution-stress-head">
      <div>
        <strong>${result.passed ? "Stress 테스트 통과" : "Stress mismatch 확인 필요"}</strong>
        <p>${escapeHtml(result.profile || "hidden")} · ${escapeHtml(result.iterations || 0)}회 · ${escapeHtml(duration)} · mismatch ${escapeHtml(result.mismatchCount || 0)}</p>
      </div>
      <button type="button" data-stress-rerun>다시 Stress 실행</button>
    </div>
    <div class="solution-summary-chips">
      <span>run ${escapeHtml(result.stressRunId || "-")}</span>
      <span>${escapeHtml(result.checkedSolutions?.length || 0)} solutions</span>
      <span>${escapeHtml(result.durationSeconds || "-")}s limit</span>
    </div>
    ${
      mismatches.length
        ? `<div class="stress-mismatch-list">
            ${mismatches.map(renderStressMismatchCard).join("")}
          </div>`
        : `<p>현재 generator seed 범위에서는 기대 결과와 다른 솔루션을 찾지 못했습니다.</p>`
    }
  `;
  panel.querySelector("[data-stress-rerun]")?.addEventListener("click", () => {
    resourceCallbacks.openSolutionStressModal();
  });
  for (const button of panel.querySelectorAll("[data-stress-preview]")) {
    button.addEventListener("click", () => {
      void resourceCallbacks.withErrors(
        () => resourceCallbacks.openStressMismatchModal(
          button.dataset.stressPreview,
          button.dataset.stressSolutionKey,
          button.dataset.stressAppendMode || null
        ),
        "Stress mismatch를 여는 중입니다."
      );
    });
  }
}
function renderStressMismatchCard(item) {
  const caseId = item.caseId || "";
  const solutionKey = item.solutionKey || "";
  const seed = item.seed ?? "-";
  return `
    <article class="stress-mismatch-card">
      <div class="stress-mismatch-title">
        <strong>${escapeHtml(item.solution || "solution")}</strong>
        <span>${escapeHtml(item.expectedStatus || "-")} → ${escapeHtml(item.actualStatus || "-")}</span>
      </div>
      <div class="stress-mismatch-meta">
        <span>case ${escapeHtml(caseId)}</span>
        <span>seed ${escapeHtml(seed)}</span>
        <span>${escapeHtml(item.generatorCaseName || "generator")}</span>
      </div>
      ${item.message ? `<p>${escapeHtml(normalizeErrorDetail(item.message))}</p>` : ""}
      <div class="stress-mismatch-actions">
        <button type="button" data-stress-preview="${escapeAttribute(caseId)}" data-stress-solution-key="${escapeAttribute(solutionKey)}">Preview</button>
        <button type="button" data-stress-preview="${escapeAttribute(caseId)}" data-stress-solution-key="${escapeAttribute(solutionKey)}" data-stress-append-mode="fixed">Fixed로 추가</button>
        <button type="button" data-stress-preview="${escapeAttribute(caseId)}" data-stress-solution-key="${escapeAttribute(solutionKey)}" data-stress-append-mode="generator">Generator 재현</button>
      </div>
    </article>
  `;
}
export function selectSolutionPath(path) {
  if (!path) return;
  state.selectedFile = path;
  state.tabSelections[selectionKey()] = path;
  rememberView();
  renderTabFiles();
  renderSolutionValidationSummary();
}
