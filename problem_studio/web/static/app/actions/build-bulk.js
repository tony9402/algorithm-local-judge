/**
 * build 일괄 작업 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { api, normalizeErrorDetail } from "../api.js";
import { updateBuildPanel } from "../build-view.js";
import { $, escapeHtml, optional } from "../dom.js";
import { showAlert } from "../feedback.js";
import {
  beginProgress,
  setProgressInsight,
  setProgressStep,
  showLastRun,
} from "../progress.js";
import { renderTabFiles } from "../resources-view.js";
import { currentProblemResult, persistProblemLastResult } from "../results.js";
import { streamProgressDetail } from "../sse.js";
import { activePackJobList, state } from "../state.js";
import { renderProblems } from "../workspace-view.js";
import { streamRequest } from "./data.js";
import { saveOpenFileIfDirty } from "./files.js";
import {
  acquireRunAllLease,
  releaseRunAllLease,
  withProblemTaskLock,
} from "./build-locks.js";
import {
  bulkMaxWorkersFromModal,
  bulkProblemIds,
  updateBulkStartButton,
  updateGlobalActionState,
} from "./build-status.js";

const bulkCallbacks = {
  openModal: () => {},
  restoreProblemLastResult: () => {},
};

let bulkCancelRequestedJobId = null;
let bulkSelectedProblemIds = new Set();

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
export function configureBulkBuildActions(callbacks = {}) {
  Object.assign(bulkCallbacks, callbacks);
}
/**
 * 일괄 작업 문제 목록 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function bulkProblemStatus(problemId) {
  const result = currentProblemResult(problemId, state.activeRepository || null);
  if (result?.fullTest?.passed === false) return "failed";
  if (result?.dirtyAfterFullTest) return "dirty";
  return "";
}

function bulkProblemStatusLabel(status) {
  if (status === "failed") return "실패";
  if (status === "dirty") return "재검증 필요";
  return "상태 없음";
}

function visibleBulkProblems() {
  const search = optional("bulkProblemSearchInput")?.value.trim().toLowerCase() || "";
  const folder = optional("bulkProblemFolderFilter")?.value || "";
  const status = optional("bulkProblemStatusFilter")?.value || "";
  return (state.problems || []).filter((problem) => {
    const text = `${problem.problemId} ${problem.title || ""} ${problem.folder || ""}`.toLowerCase();
    return (!search || text.includes(search))
      && (!folder || (problem.folder || "") === folder)
      && (!status || bulkProblemStatus(problem.problemId) === status);
  });
}

function renderBulkFolderOptions() {
  const select = optional("bulkProblemFolderFilter");
  if (!select) return;
  const selected = select.value;
  const folders = Array.from(new Set((state.problems || []).map((problem) => problem.folder || "")))
    .sort((left, right) => left.localeCompare(right, "ko"));
  select.innerHTML = escapeHtml("") + `<option value="">모든 폴더</option>${folders.map((folder) =>
    `<option value="${escapeHtml(folder)}">${escapeHtml(folder || "기본")}</option>`
  ).join("")}`;
  if (folders.includes(selected)) select.value = selected;
}

function syncBulkSelectionDataset() {
  const list = optional("bulkProblemList");
  if (list) list.dataset.selectedProblemIds = JSON.stringify(Array.from(bulkSelectedProblemIds));
}

export function renderBulkProblemList() {
  const list = $("bulkProblemList");
  const problems = state.problems || [];
  if (!problems.length) {
    syncBulkSelectionDataset();
    list.innerHTML = `<p class="muted">등록된 문제가 없습니다.</p>`;
    updateBulkStartButton();
    return;
  }
  renderBulkFolderOptions();
  const visible = visibleBulkProblems();
  if (!visible.length) {
    syncBulkSelectionDataset();
    list.innerHTML = `<p class="muted">검색·필터와 일치하는 문제가 없습니다.</p>`;
    updateBulkStartButton();
    return;
  }
  list.innerHTML = escapeHtml("") + visible
    .map(
      (problem) => {
        const status = bulkProblemStatus(problem.problemId);
        return `
        <label class="bulk-problem-option">
          <input type="checkbox" data-bulk-problem value="${escapeHtml(problem.problemId)}" ${bulkSelectedProblemIds.has(problem.problemId) ? "checked" : ""} />
          <span class="bulk-problem-copy">
            <strong>${escapeHtml(problem.problemId)} ${escapeHtml(problem.title || "")}</strong>
            <small>${escapeHtml(problem.folder || "기본")} · 버전 ${escapeHtml(problem.version || "-")} · ${escapeHtml(problem.defaultProfile || "-")} · ${escapeHtml(bulkProblemStatusLabel(status))}</small>
          </span>
        </label>
      `;
      }
    )
    .join("");
  syncBulkSelectionDataset();
  for (const input of document.querySelectorAll("[data-bulk-problem]")) {
    input.addEventListener("change", () => {
      if (input.checked) bulkSelectedProblemIds.add(input.value);
      else bulkSelectedProblemIds.delete(input.value);
      syncBulkSelectionDataset();
      updateBulkStartButton();
    });
  }
  updateBulkStartButton();
}

function bindBulkProblemControls() {
  const search = optional("bulkProblemSearchInput");
  if (!search || search.dataset.bulkBound === "true") return;
  search.dataset.bulkBound = "true";
  search.addEventListener("input", renderBulkProblemList);
  optional("bulkProblemFolderFilter")?.addEventListener("change", renderBulkProblemList);
  optional("bulkProblemStatusFilter")?.addEventListener("change", renderBulkProblemList);
  optional("bulkSelectAllButton")?.addEventListener("click", () => {
    bulkSelectedProblemIds = new Set((state.problems || []).map((problem) => problem.problemId));
    renderBulkProblemList();
  });
  optional("bulkDeselectAllButton")?.addEventListener("click", () => {
    bulkSelectedProblemIds.clear();
    renderBulkProblemList();
  });
}
/**
 * 작업 공간 build 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 */
export function openWorkspaceBuildModal() {
  if (!bulkProblemIds().length) throw new Error("빌드할 문제가 없습니다.");
  $("bulkPackIdInput").value = optional("packIdInput")?.value.trim() || "basic";
  $("bulkVerifyProfileInput").value = optional("packVerifyProfileInput")?.value.trim() || "hidden";
  $("bulkMaxWorkersInput").value = "";
  $("bulkProblemSearchInput").value = "";
  $("bulkProblemFolderFilter").value = "";
  $("bulkProblemStatusFilter").value = "";
  bulkSelectedProblemIds = new Set((state.problems || []).map((problem) => problem.problemId));
  bindBulkProblemControls();
  renderBulkProblemList();
  bulkCallbacks.openModal("workspaceBuildModal");
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
    failureStage: item.failureStage || "",
    failureStageLabel: item.failureStageLabel || "",
    failureDetails: item.failureDetails || [],
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
  state.lastBulkBuildResult = result;
  const checkedAt = Date.now();
  for (const item of result.problems || []) {
    persistBulkProblemResult(item, checkedAt);
  }
  if (state.selectedProblem) bulkCallbacks.restoreProblemLastResult(state.selectedProblem);
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
    .map((item) => {
      const stage = item.failureStageLabel || item.failureStage || "검증";
      return `${item.problemId} · ${stage}: ${item.summary || "실패"}`;
    })
    .join("\n");
  const remaining = failed > 4 ? `\n외 ${failed - 4}개 문제 실패` : "";
  const packSummary = packs ? `${packs}개 팩 생성` : "팩 생성 안 함";
  return `${total}개 중 ${failed}개 문제 실패 · ${packSummary}\n${failedProblems}${remaining}`;
}
function persistBulkJob(job, problemIds, details = {}) {
  state.activeBulkJob = {
    jobId: job.jobId,
    title: job.title || "전체 문제 테스트/팩 빌드",
    status: job.status,
    cancelRequested: Boolean(job.cancelRequested),
    cancelRequestedAt: job.cancelRequested ? Date.now() : state.activeBulkJob?.cancelRequestedAt,
    problemIds,
    packId: details.packId,
    verifyProfile: details.verifyProfile,
    startedAt: state.activeBulkJob?.startedAt || Date.now(),
  };
  updateGlobalActionState();
  updateBuildPanel();
}
/**
 * 일괄 작업 작업 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 */
function clearBulkJob() {
  state.activeBulkJob = null;
  bulkCancelRequestedJobId = null;
  updateGlobalActionState();
  updateBuildPanel();
}
async function waitForBulkJob(job, problemIds, details) {
  persistBulkJob(job, problemIds, details);
  try {
    while (true) {
      const current = await api(`/api/workspace/packs/jobs/${encodeURIComponent(job.jobId)}`);
      if (current.status === "succeeded") {
        clearBulkJob();
        const result = current.result || {};
        for (const [index, item] of (result.problems || []).entries()) {
          setProgressStep(index, item.passed ? "success" : "error", item.summary || "");
        }
        setProgressInsight(
          result.passed ? "전체 문제 팩 빌드 완료" : "수정할 문제가 있습니다",
          bulkBuildSummary(result)
        );
        return result;
      }
      if (current.status === "failed") {
        clearBulkJob();
        const detail = normalizeErrorDetail(current.error);
        setProgressInsight("전체 문제 팩 빌드 실패", detail);
        throw new Error(detail);
      }
      if (current.status === "cancelled") {
        clearBulkJob();
        setProgressInsight("전체 문제 팩 빌드 취소됨", "실행 중인 작업을 중단했습니다.");
        showLastRun(
          "전체 문제 테스트/팩 빌드 취소됨",
          "실행 중인 전체 문제 테스트/팩 빌드를 중단했습니다.",
          "error"
        );
        throw new Error("전체 문제 테스트/팩 빌드를 취소했습니다.");
      }
      if (current.status === "cancelling") {
        setProgressInsight("전체 문제 빌드 취소 중", "서버가 취소 요청을 처리하고 있습니다.");
      }
      if (current.lastLog || current.progress?.message) {
        updateBulkProgressFromLog(current.lastLog || current.progress.message, problemIds);
      }
      persistBulkJob(current, problemIds, details);
      await sleep(bulkCancelRequestedJobId === job.jobId ? 350 : 750);
    }
  } catch (error) {
    clearBulkJob();
    throw error;
  }
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
  const job = await api(
    "/api/workspace/packs/build-all",
    {
      method: "POST",
      body: JSON.stringify({
        pack_id: packId,
        verify_profile: verifyProfile,
        force: false,
        max_workers: bulkMaxWorkersFromModal(),
        problem_ids: problemIds,
      }),
    }
  );
  const result = await waitForBulkJob(job, problemIds, { packId, verifyProfile });
  /*
  The stream endpoint remains available for compatibility and tests that exercise the
  lower-level SSE contract:
  await streamRequest(
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
  */
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
export async function cancelActiveBulkJob() {
  const job = state.activeBulkJob;
  if (!job?.jobId) return;
  const current = await api(`/api/workspace/packs/jobs/${encodeURIComponent(job.jobId)}/cancel`, {
    method: "POST",
  });
  bulkCancelRequestedJobId = job.jobId;
  persistBulkJob(current, job.problemIds || [], {
    packId: job.packId,
    verifyProfile: job.verifyProfile,
  });
  showLastRun("전체 문제 빌드 취소 요청", "실행 중인 전체 문제 테스트/팩 빌드 중단을 요청했습니다.", "running");
  setProgressInsight("전체 문제 빌드 취소 중", "서버가 취소 요청을 접수했습니다.");
  updateGlobalActionState();
}
export async function buildAllPacksOnce(problemIds = bulkProblemIds()) {
  if (activePackJobList().length) throw new Error("팩 빌드 진행 중에는 전체 문제 빌드를 시작할 수 없습니다.");
  return withProblemTaskLock(async () => {
    const lease = acquireRunAllLease("전체 문제");
    if (!lease) throw new Error("이미 다른 탭에서 전체 테스트가 실행 중입니다.");
    updateGlobalActionState();
    try {
      return await buildAllPacks(problemIds);
    } finally {
      releaseRunAllLease(lease);
      updateGlobalActionState();
    }
  }, "전체 문제");
}
