import { api, normalizeErrorDetail } from "../api.js";
import { updateBuildPanel } from "../build-view.js";
import {
  formatOperationFailure,
  showAlert,
  showResult,
} from "../feedback.js";
import { showLastRun } from "../progress.js";
import { persistProblemLastResult } from "../results.js";
import { PACK_JOB_KEY, PACK_OUTPUT_DIR, state } from "../state.js";
import { readStorage, removeStorage, writeStorage } from "../storage.js";
import { packJobSummary, updateGlobalActionState } from "./build-status.js";

export function persistPackJob(job, problemId, details = {}) {
  const previous = state.activePackJob || {};
  state.activePackJob = {
    jobId: job.jobId,
    problemId,
    repositoryName: state.activeRepository || null,
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

export function clearPackJob() {
  state.activePackJob = null;
  removeStorage(PACK_JOB_KEY);
  if (state.packPollTimer) {
    window.clearTimeout(state.packPollTimer);
    state.packPollTimer = null;
  }
  updateGlobalActionState();
  updateBuildPanel();
}

function markPackJobStale(job, problemId) {
  state.stalePackJob = {
    ...job,
    problemId,
    packId: state.activePackJob?.packId || job.packId,
    outputDir: state.activePackJob?.outputDir || PACK_OUTPUT_DIR,
  };
  clearPackJob();
  showLastRun(
    "팩 빌드 상태 만료",
    `${packJobSummary(state.stalePackJob)} · 오래된 작업이라 상태 추적을 종료했습니다.`,
    "error",
    { problemId }
  );
  updateGlobalActionState();
  updateBuildPanel();
}

export async function dismissStalePackJob() {
  const job = state.stalePackJob;
  state.stalePackJob = null;
  updateGlobalActionState();
  updateBuildPanel();
  if (!job?.jobId || !job?.problemId) return;
  try {
    await api(
      `/api/problems/${encodeURIComponent(job.problemId)}/packs/jobs/${encodeURIComponent(job.jobId)}`,
      { method: "DELETE" }
    );
  } catch {
    // The job may already be gone after a server restart or retention cleanup.
  }
}

export function schedulePackJobPoll(problemId, jobId, delay = 1500) {
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
    if (job.stale || job.status === "stale") {
      markPackJobStale(job, problemId);
      return;
    }
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
    if (job.status === "cancelled") {
      clearPackJob();
      showLastRun("팩 빌드 취소됨", `${problemId} 문제 팩 빌드를 중단했습니다.`, "error", {
        problemId,
      });
      showAlert("팩 빌드를 취소했습니다.", "info", { title: "팩 빌드 취소" });
      return;
    }
    persistPackJob(job, problemId);
    schedulePackJobPoll(problemId, jobId);
  } catch (error) {
    if (error.status === 404) {
      markPackJobStale(
        {
          jobId,
          problemId,
          packId: state.activePackJob?.packId,
          outputDir: state.activePackJob?.outputDir,
          status: "stale",
          previousStatus: "unknown",
          stale: true,
          error: error.message,
        },
        problemId
      );
      return;
    }
    clearPackJob();
    showAlert(error.message, "error", { title: "팩 빌드 상태 확인 실패", timeout: 9000 });
  }
}

export function syncPackJobFromStorage() {
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
  if ((job.repositoryName || null) !== (state.activeRepository || null)) {
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

export async function cancelActivePackJob() {
  const job = state.activePackJob;
  if (!job?.jobId || !job?.problemId) return;
  await api(
    `/api/problems/${encodeURIComponent(job.problemId)}/packs/jobs/${encodeURIComponent(job.jobId)}/cancel`,
    { method: "POST" }
  );
  showLastRun("팩 빌드 취소 요청", `${packJobSummary(job)} · 중단을 요청했습니다.`, "running", {
    problemId: job.problemId,
  });
  schedulePackJobPoll(job.problemId, job.jobId, 250);
  updateGlobalActionState();
}
