/**
 * build 화면 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { escapeHtml, optional, setText } from "./dom.js";
import { currentProblemResult, hasFreshFullTest } from "./results.js";
import { PACK_OUTPUT_DIR, STATUS_LABELS, activePackJobForProblem, state } from "./state.js";
import { updateEditorPanelMode } from "./tabs-view.js";
import { renderControlPolicies } from "./control-policy.js";

const buildCallbacks = {
  formatTime: () => "",
  packJobSummary: () => "",
};
const STAGE_LABELS = {
  cases: "cases.yml 검사",
  tools: "도구 컴파일",
  validation: "데이터 생성+검증",
  solutions: "솔루션 기대 결과",
  pack: "팩 생성",
  unknown: "검증",
};
export function configureBuildView(callbacks = {}) {
  Object.assign(buildCallbacks, callbacks);
}
function statusLabel(status) {
  return STATUS_LABELS[status] || status || "-";
}
function problemDisplayName(problemId) {
  const problem = (state.problems || []).find((item) => item.problemId === problemId);
  return [problemId, problem?.title].filter(Boolean).join(" · ");
}
function failureStageLabel(item) {
  return item?.failureStageLabel || STAGE_LABELS[item?.failureStage] || item?.failureStage || "검증";
}
function failureDetails(item) {
  return Array.isArray(item?.failureDetails) ? item.failureDetails : [];
}
function detailTitle(detail) {
  if (detail.source) return detail.source;
  if (detail.target) return detail.target;
  return detail.label || "실패 상세";
}
function detailMeta(detail) {
  const chunks = [];
  if (detail.expectedStatus || detail.actualStatus) {
    chunks.push(`기대 ${statusLabel(detail.expectedStatus)} · 실제 ${statusLabel(detail.actualStatus)}`);
  }
  if (detail.runId) chunks.push(`run ${detail.runId}`);
  if (detail.caseCount) chunks.push(`${detail.caseCount}개 case`);
  return chunks.join(" · ");
}
function renderDetail(detail) {
  const meta = detailMeta(detail);
  return `
    <li class="build-diagnostic-detail">
      <strong>${escapeHtml(detailTitle(detail))}</strong>
      ${meta ? `<span>${escapeHtml(meta)}</span>` : ""}
      ${detail.message ? `<p>${escapeHtml(detail.message)}</p>` : ""}
    </li>
  `;
}
function renderProblemDiagnostic(item, index) {
  const details = failureDetails(item);
  const problemId = item.problemId || state.selectedProblem || "-";
  const stage = failureStageLabel(item);
  return `
    <details class="build-diagnostic-problem" open>
      <summary>
        <span class="build-diagnostic-index">${index + 1}</span>
        <span class="build-diagnostic-title">
          <strong>${escapeHtml(problemDisplayName(problemId))}</strong>
          <small>${escapeHtml(stage)}에서 확인 필요</small>
        </span>
        <span class="build-diagnostic-status">실패</span>
      </summary>
      <p class="build-diagnostic-summary">${escapeHtml(item.summary || "실패한 검증 항목을 확인하세요.")}</p>
      ${
        details.length
          ? `<ul class="build-diagnostic-details">${details.map(renderDetail).join("")}</ul>`
          : ""
      }
    </details>
  `;
}
function selectedProblemDiagnostic(fullTest) {
  if (!fullTest || fullTest.passed) return null;
  return {
    problemId: state.selectedProblem,
    passed: false,
    summary: fullTest.summary || "전체 테스트가 실패했습니다.",
    failureStage: fullTest.failureStage || "unknown",
    failureStageLabel: fullTest.failureStageLabel || "",
    failureDetails: fullTest.failureDetails || [],
  };
}
function selectedProblemBulkDiagnostic() {
  if (!state.selectedProblem) return null;
  const item = (state.lastBulkBuildResult?.problems || []).find(
    (problem) => problem.problemId === state.selectedProblem && !problem.passed
  );
  if (!item) return null;
  return {
    problemId: state.selectedProblem,
    passed: false,
    summary: item.summary || "전체 문제 테스트가 실패했습니다.",
    failureStage: item.failureStage || "unknown",
    failureStageLabel: item.failureStageLabel || "",
    failureDetails: item.failureDetails || [],
  };
}
function renderBuildDiagnostics(fullTest) {
  const panel = optional("buildDiagnostics");
  if (!panel) return;
  if (state.selectedTab !== "build") {
    panel.classList.add("hidden");
    return;
  }

  const current = selectedProblemDiagnostic(fullTest) || (fullTest ? null : selectedProblemBulkDiagnostic());
  if (!current) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }

  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div class="build-diagnostics-heading">
      <div>
        <span>현재 문제 진단</span>
        <strong>선택한 문제의 실패 단계와 상세만 표시합니다.</strong>
      </div>
      <span class="build-diagnostics-count">${escapeHtml(failureStageLabel(current))} 확인 필요</span>
    </div>
    <div class="build-diagnostic-list">
      ${renderProblemDiagnostic(current, 0)}
    </div>
  `;
}
/**
 * 다운로드 link 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 *
 * @param {any} link 다운로드 link을 계산하거나 검증할 때 필요한 link 입력입니다.
 * @param {any} pack 다운로드 link을 계산하거나 검증할 때 필요한 문제팩 입력입니다.
 * @param {any} fallbackLabel 다운로드 link을 계산하거나 검증할 때 필요한 fallback label 입력입니다.
 */
export function updateDownloadLink(link, pack, fallbackLabel = "다운로드") {
  if (!link) return;
  link.classList.toggle("hidden", !pack?.downloadUrl);
  if (pack?.downloadUrl) {
    link.href = pack.downloadUrl;
    link.textContent = `${pack.archiveLabel || fallbackLabel} 다운로드`;
  }
}
/**
 * build 대시보드 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
export function updateBuildDashboard() {
  const dashboard = optional("buildDashboard");
  if (!dashboard || state.selectedTab !== "build") return;
  const result = currentProblemResult();
  const fullTest = result?.fullTest || state.lastFullTest;
  const pack = state.lastPackResult || result?.lastPackResult;
  const activePackJob = activePackJobForProblem();
  const profile = optional("packVerifyProfileInput")?.value.trim() || "hidden";
  let tone = "neutral";
  let title = "전체 테스트 필요";
  let summary = "팩 빌드 전에 현재 문제의 전체 테스트를 실행해야 합니다.";
  let testState = "대기";
  let testDetail = "아직 통과 기록이 없습니다.";

  if (activePackJob) {
    tone = "running";
    title = "팩 빌드 진행 중";
    summary = buildCallbacks.packJobSummary(activePackJob);
    testState = "빌드 중";
    testDetail = "완료되면 최근 팩과 다운로드 링크가 갱신됩니다.";
  } else if (hasFreshFullTest()) {
    tone = "success";
    title = "전체 테스트 통과";
    summary = fullTest?.summary || "현재 문제 팩을 빌드할 수 있습니다.";
    testState = "통과";
    testDetail = fullTest?.checkedAt ? `${buildCallbacks.formatTime(fullTest.checkedAt)} 확인` : "검증 완료";
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
    testDetail = fullTest.checkedAt ? `${buildCallbacks.formatTime(fullTest.checkedAt)} 실패` : "검증 실패";
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
    activePackJob ? buildCallbacks.packJobSummary(activePackJob) : pack?.archiveLabel || "아직 없음"
  );
  updateDownloadLink(optional("buildDashboardDownloadLink"), pack, "팩 파일");
  renderBuildDiagnostics(fullTest);
}
/**
 * build panel 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
export function updateBuildPanel() {
  const panel = optional("buildPanel");
  if (!panel) return;
  const visible = state.selectedTab === "build";
  panel.classList.toggle("hidden", !visible);
  if (!visible) {
    updateEditorPanelMode();
    return;
  }

  const result = currentProblemResult();
  const activePackJob = activePackJobForProblem();
  const status = optional("buildValidationStatus");
  const output = optional("packOutputLabel");
  const link = optional("packDownloadLink");
  if (output) output.textContent = PACK_OUTPUT_DIR;
  if (status) {
    if (activePackJob) {
      status.textContent = `팩 빌드 진행 중입니다. ${buildCallbacks.packJobSummary(activePackJob)}`;
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
  renderControlPolicies(["build.pack"]);
}
