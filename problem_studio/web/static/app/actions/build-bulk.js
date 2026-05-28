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
import { persistProblemLastResult } from "../results.js";
import { streamProgressDetail } from "../sse.js";
import { state } from "../state.js";
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

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function configureBulkBuildActions(callbacks = {}) {
  Object.assign(bulkCallbacks, callbacks);
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

export function openWorkspaceBuildModal() {
  if (!bulkProblemIds().length) throw new Error("빌드할 문제가 없습니다.");
  $("bulkPackIdInput").value = optional("packIdInput")?.value.trim() || "basic";
  $("bulkVerifyProfileInput").value = optional("packVerifyProfileInput")?.value.trim() || "hidden";
  $("bulkMaxWorkersInput").value = "";
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
    .map((item) => `${item.problemId}: ${item.summary || "실패"}`)
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
  if (state.activePackJob) throw new Error("팩 빌드 진행 중에는 전체 문제 빌드를 시작할 수 없습니다.");
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
  });
}
