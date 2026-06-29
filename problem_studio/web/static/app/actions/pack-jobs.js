/**
 * 문제팩 작업 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { api, normalizeErrorDetail } from "../api.js";
import { updateBuildPanel } from "../build-view.js";
import {
  formatOperationFailure,
  showAlert,
  showResult,
} from "../feedback.js";
import { showLastRun } from "../progress.js";
import { persistProblemLastResult } from "../results.js";
import {
  PACK_JOB_KEY,
  PACK_OUTPUT_DIR,
  activePackJobForProblem,
  problemStateKey,
  stalePackJobForProblem,
  state,
} from "../state.js";
import { readStorage, removeStorage, writeStorage } from "../storage.js";
import { packJobSummary, updateGlobalActionState } from "./build-status.js";

function jobRepositoryName(job) {
  return job?.repositoryName ?? job?.target?.repositoryName ?? null;
}

function isCurrentProblemContext(problemId, repositoryName) {
  return state.selectedProblem === problemId && (state.activeRepository || null) === (repositoryName || null);
}

function readPackJobMap() {
  const stored = readStorage(PACK_JOB_KEY);
  if (!stored || typeof stored !== "object") return {};
  if (stored.jobsByProblem && typeof stored.jobsByProblem === "object") {
    return stored.jobsByProblem;
  }
  if (stored.jobId && stored.problemId) {
    return {
      [problemStateKey(stored.problemId, stored.repositoryName || null)]: stored,
    };
  }
  return {};
}

function writePackJobMap(jobsByProblem) {
  const keys = Object.keys(jobsByProblem || {});
  if (!keys.length) {
    removeStorage(PACK_JOB_KEY);
    return;
  }
  writeStorage(PACK_JOB_KEY, {
    jobsByProblem,
    updatedAt: Date.now(),
  });
}

function setSelectedPackJobAliases() {
  state.activePackJob = activePackJobForProblem();
  state.stalePackJob = stalePackJobForProblem();
  const key = problemStateKey();
  state.packPollTimer = key ? state.packPollTimersByProblem?.[key] || null : null;
}

function clearPackPollTimer(problemId, repositoryName) {
  const key = problemStateKey(problemId, repositoryName);
  const timer = state.packPollTimersByProblem?.[key];
  if (timer) window.clearTimeout(timer);
  const timers = { ...(state.packPollTimersByProblem || {}) };
  delete timers[key];
  state.packPollTimersByProblem = timers;
  setSelectedPackJobAliases();
}

function currentRepositoryMatches(repositoryName) {
  return (state.activeRepository || null) === (repositoryName || null);
}

export function persistPackJob(job, problemId, details = {}) {
  const repositoryName =
    details.repositoryName ?? jobRepositoryName(job) ?? state.activeRepository ?? null;
  const key = problemStateKey(problemId, repositoryName);
  const previous = state.activePackJobsByProblem?.[key] || {};
  const nextJob = {
    ...previous,
    jobId: job.jobId,
    title: job.title || previous.title,
    status: job.status || previous.status,
    problemId,
    repositoryName,
    packId: details.packId || job.target?.packId || previous.packId,
    outputDir: details.outputDir || previous.outputDir,
    cancelRequested: Boolean(job.cancelRequested),
    startedAt: previous.startedAt || Date.now(),
  };
  state.activePackJobsByProblem = {
    ...(state.activePackJobsByProblem || {}),
    [key]: nextJob,
  };
  setSelectedPackJobAliases();
  const stored = readPackJobMap();
  stored[key] = nextJob;
  writePackJobMap(stored);
  if (isCurrentProblemContext(problemId, repositoryName)) {
    showLastRun(
      "팩 빌드 진행 중",
      `${packJobSummary(nextJob)} · 완료되면 자동으로 알려드립니다.`,
      "running",
      { problemId }
    );
  }
  updateGlobalActionState();
  updateBuildPanel();
}
/**
 * 문제팩 작업 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 */
export function clearPackJob(
  problemId = state.selectedProblem,
  repositoryName = state.activeRepository || null
) {
  const key = problemStateKey(problemId, repositoryName);
  if (!key) return;
  const next = { ...(state.activePackJobsByProblem || {}) };
  delete next[key];
  state.activePackJobsByProblem = next;
  const stored = readPackJobMap();
  delete stored[key];
  writePackJobMap(stored);
  clearPackPollTimer(problemId, repositoryName);
  setSelectedPackJobAliases();
  updateGlobalActionState();
  updateBuildPanel();
}
function markPackJobStale(job, problemId, repositoryName = state.activeRepository || null) {
  const key = problemStateKey(problemId, repositoryName);
  const active = activePackJobForProblem(problemId, repositoryName);
  state.stalePackJobsByProblem = {
    ...(state.stalePackJobsByProblem || {}),
    [key]: {
      ...job,
      problemId,
      repositoryName,
      packId: active?.packId || job.packId,
      outputDir: active?.outputDir || PACK_OUTPUT_DIR,
    },
  };
  clearPackJob(problemId, repositoryName);
  setSelectedPackJobAliases();
  if (isCurrentProblemContext(problemId, repositoryName)) {
    showLastRun(
      "팩 빌드 상태 만료",
      `${packJobSummary(stalePackJobForProblem(problemId, repositoryName))} · 오래된 작업이라 상태 추적을 종료했습니다.`,
      "error",
      { problemId }
    );
  }
  updateGlobalActionState();
  updateBuildPanel();
}
export async function dismissStalePackJob(
  problemId = state.selectedProblem,
  repositoryName = state.activeRepository || null
) {
  const key = problemStateKey(problemId, repositoryName);
  const job = stalePackJobForProblem(problemId, repositoryName);
  const next = { ...(state.stalePackJobsByProblem || {}) };
  delete next[key];
  state.stalePackJobsByProblem = next;
  setSelectedPackJobAliases();
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
export function schedulePackJobPoll(
  problemId,
  jobId,
  delay = 1500,
  repositoryName = state.activeRepository || null
) {
  const key = problemStateKey(problemId, repositoryName);
  clearPackPollTimer(problemId, repositoryName);
  const timer = window.setTimeout(() => {
    void pollPackJob(problemId, jobId, repositoryName);
  }, delay);
  state.packPollTimersByProblem = {
    ...(state.packPollTimersByProblem || {}),
    [key]: timer,
  };
  setSelectedPackJobAliases();
}
async function pollPackJob(problemId, jobId, repositoryName = state.activeRepository || null) {
  if (!currentRepositoryMatches(repositoryName)) {
    clearPackPollTimer(problemId, repositoryName);
    return;
  }
  try {
    const job = await api(
      `/api/problems/${encodeURIComponent(problemId)}/packs/jobs/${encodeURIComponent(jobId)}`
    );
    if (job.stale || job.status === "stale") {
      markPackJobStale(job, problemId, repositoryName);
      return;
    }
    if (job.status === "succeeded") {
      clearPackJob(problemId, repositoryName);
      const label = job.result?.archiveLabel || "팩 파일";
      const packResult = {
        ...job.result,
        downloadUrl: `/api/problems/${encodeURIComponent(problemId)}/packs/jobs/${encodeURIComponent(jobId)}/download`,
        finishedAt: Date.now(),
      };
      persistProblemLastResult({ lastPackResult: packResult }, problemId, repositoryName);
      if (isCurrentProblemContext(problemId, repositoryName)) {
        state.lastPackResult = packResult;
        updateBuildPanel();
        showLastRun("팩 빌드 완료", `${problemId} 문제 팩이 생성되었습니다: ${label}`, "success", {
          problemId,
        });
        showResult(`팩 빌드 완료: ${label}`, "summary success");
      }
      return;
    }
    if (job.status === "failed") {
      clearPackJob(problemId, repositoryName);
      const detail = normalizeErrorDetail(job.error);
      if (isCurrentProblemContext(problemId, repositoryName)) {
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
      }
      return;
    }
    if (job.status === "cancelled") {
      clearPackJob(problemId, repositoryName);
      if (isCurrentProblemContext(problemId, repositoryName)) {
        showLastRun("팩 빌드 취소됨", `${problemId} 문제 팩 빌드를 중단했습니다.`, "error", {
          problemId,
        });
        showAlert("팩 빌드를 취소했습니다.", "info", { title: "팩 빌드 취소" });
      }
      return;
    }
    persistPackJob(job, problemId, { repositoryName });
    schedulePackJobPoll(problemId, jobId, 1500, repositoryName);
  } catch (error) {
    if (error.status === 404) {
      const active = activePackJobForProblem(problemId, repositoryName);
      markPackJobStale(
        {
          jobId,
          problemId,
          repositoryName,
          packId: active?.packId,
          outputDir: active?.outputDir,
          status: "stale",
          previousStatus: "unknown",
          stale: true,
          error: error.message,
        },
        problemId,
        repositoryName
      );
      return;
    }
    clearPackJob(problemId, repositoryName);
    if (isCurrentProblemContext(problemId, repositoryName)) {
      showAlert(error.message, "error", { title: "팩 빌드 상태 확인 실패", timeout: 9000 });
    }
  }
}
export function syncPackJobFromStorage() {
  const repositoryName = state.activeRepository || null;
  const stored = readPackJobMap();
  const next = {};
  for (const [key, job] of Object.entries(stored)) {
    if ((job.repositoryName || null) !== repositoryName) continue;
    next[key] = job;
  }
  for (const [key, timer] of Object.entries(state.packPollTimersByProblem || {})) {
    if (!next[key]) window.clearTimeout(timer);
  }
  state.activePackJobsByProblem = next;
  state.packPollTimersByProblem = Object.fromEntries(
    Object.entries(state.packPollTimersByProblem || {}).filter(([key]) => next[key])
  );
  setSelectedPackJobAliases();
  updateGlobalActionState();
  updateBuildPanel();
  for (const job of Object.values(next)) {
    const key = problemStateKey(job.problemId, job.repositoryName || null);
    if (!state.packPollTimersByProblem?.[key]) {
      schedulePackJobPoll(job.problemId, job.jobId, 250, job.repositoryName || null);
    }
  }
}
export async function cancelActivePackJob(
  problemId = state.selectedProblem,
  repositoryName = state.activeRepository || null
) {
  const job = activePackJobForProblem(problemId, repositoryName);
  if (!job?.jobId || !job?.problemId) return;
  await api(
    `/api/problems/${encodeURIComponent(job.problemId)}/packs/jobs/${encodeURIComponent(job.jobId)}/cancel`,
    { method: "POST" }
  );
  showLastRun("팩 빌드 취소 요청", `${packJobSummary(job)} · 중단을 요청했습니다.`, "running", {
    problemId: job.problemId,
  });
  schedulePackJobPoll(job.problemId, job.jobId, 250, repositoryName);
  updateGlobalActionState();
}
