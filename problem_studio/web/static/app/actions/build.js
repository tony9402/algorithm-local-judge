import { api, normalizeErrorDetail } from "../api.js";
import { updateBuildPanel } from "../build-view.js";
import { $ } from "../dom.js";
import {
  clearOutput,
  formatOperationFailure,
  showAlert,
  showResult,
} from "../feedback.js";
import {
  beginProgress,
  setProgressInsight,
  setProgressStep,
  showLastRun,
  updateProgressFromJob,
} from "../progress.js";
import { renderTabFiles } from "../resources-view.js";
import { PACK_OUTPUT_DIR, state } from "../state.js";
import { runQueuedJob } from "../jobs-view.js";
import {
  failedSolutionChecks,
  formatSolutionFailureSummary,
} from "../solution-status.js";
import { saveOpenFileIfDirty } from "./files.js";
import { hasFreshFullTest, persistProblemLastResult } from "../results.js";
import { configureBulkBuildActions } from "./build-bulk.js";
import {
  acquireRunAllLease,
  currentRunAllLock,
  releaseRunAllLease,
  withProblemTaskLock,
} from "./build-locks.js";
import { updateGlobalActionState } from "./build-status.js";
import { persistPackJob, schedulePackJobPoll } from "./pack-jobs.js";

export {
  formatTime,
  packJobSummary,
  selectedBulkProblemIdsFromModal,
  updateBulkStartButton,
  updateGlobalActionState,
} from "./build-status.js";
export {
  clearPackJob,
  cancelActivePackJob,
  dismissStalePackJob,
  syncPackJobFromStorage,
} from "./pack-jobs.js";
export { buildAllPacksOnce, cancelActiveBulkJob, openWorkspaceBuildModal } from "./build-bulk.js";

export function configureBuildActions(callbacks = {}) {
  configureBulkBuildActions(callbacks);
}

async function runAllChecks() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  clearOutput();
  const steps = [
    { label: "cases.yml 검사", status: "running" },
    { label: "도구 컴파일", status: "pending" },
    { label: "모든 데이터 생성+검증", status: "pending" },
    { label: "기대 결과 솔루션 검증", status: "pending" },
  ];
  beginProgress(`전체 테스트 · ${state.selectedProblem}번 문제`, steps);
  try {
    setProgressInsight("작업 센터", "전체 테스트를 서버 queue에서 실행합니다.");
    const result = await runQueuedJob(
      `/api/problems/${state.selectedProblem}/checks/jobs`,
      { force: false },
      { label: "전체 테스트", onProgress: updateProgressFromJob }
    );
    const cases = result.cases || {};
    const tools = result.tools || {};
    const validation = result.validation || {};
    const verification = result.verification || {};
    setProgressStep(0, "success", `${cases.profiles?.length || 0}개 profile 확인`);
    setProgressStep(1, "success", `${Object.keys(tools.labels || {}).length}개 도구 컴파일`);
    setProgressStep(
      2,
      "success",
      `${validation.profileCount || 0}개 profile · ${validation.caseCount || 0}개 데이터 검증`
    );
    setProgressStep(
      3,
      verification.passed ? "success" : "error",
      verification.passed
        ? `${verification.checks?.length || 0}개 솔루션 확인`
        : `${failedSolutionChecks(verification).length}개 솔루션 기대 결과 불일치`
    );

    const summary = [
      `${cases.profiles?.length || 0}개 profile 확인`,
      `${Object.keys(tools.labels || {}).length}개 도구 컴파일`,
      `${validation.profileCount || 0}개 profile · ${validation.caseCount || 0}개 데이터 검증`,
      `${verification.checks?.length || 0}개 솔루션 검증`,
    ].join(" · ");
    const solutionFailureSummary = formatSolutionFailureSummary(verification);
    setProgressInsight(
      verification.passed ? "전체 테스트 통과" : "수정할 항목이 있습니다",
      verification.passed ? summary : solutionFailureSummary
    );
    showLastRun(
      verification.passed ? "전체 테스트 완료" : "전체 테스트 실패",
      verification.passed ? summary : solutionFailureSummary,
      verification.passed ? "success" : "error"
    );
    if (verification.passed) {
      state.lastFullTest = {
        passed: true,
        summary,
        checkedAt: Date.now(),
        profile: "all",
      };
      persistProblemLastResult({
        fullTest: state.lastFullTest,
        dirtyAfterFullTest: false,
        dirtyReason: "",
      });
      updateBuildPanel();
      renderTabFiles();
      showResult("전체 테스트가 완료되었습니다.", "summary success");
    } else {
      state.lastFullTest = {
        passed: false,
        summary: solutionFailureSummary,
        checkedAt: Date.now(),
        profile: "all",
      };
      persistProblemLastResult({
        fullTest: state.lastFullTest,
        dirtyAfterFullTest: true,
        dirtyReason: "전체 테스트가 실패했습니다.",
      });
      updateBuildPanel();
      renderTabFiles();
      const failedCount = failedSolutionChecks(verification).length;
      showAlert(`솔루션 기대 결과가 ${failedCount}개 일치하지 않습니다. 각 솔루션의 채점 결과에서 상세를 확인하세요.`, "error", {
        title: "전체 테스트 실패",
        timeout: 5000,
      });
    }
  } catch (error) {
    const runningIndex = state.progress.steps.findIndex((step) => step.status === "running");
    const failedStep = runningIndex >= 0 ? state.progress.steps[runningIndex]?.label : "";
    const detail = normalizeErrorDetail(error.message);
    if (runningIndex >= 0) setProgressStep(runningIndex, "error", detail);
    setProgressInsight(
      "수정할 항목이 있습니다",
      detail || "실패한 단계를 확인한 뒤 다시 실행하세요."
    );
    showLastRun(
      "전체 테스트 실패",
      formatOperationFailure(detail, [
        failedStep ? `실패 단계: ${failedStep}` : "",
        state.lastStreamDetail ? `마지막 단계: ${state.lastStreamDetail}` : "",
        "관련 대상: cases.yml, generator, validator, checker, solutions",
      ]),
      "error"
    );
    throw error;
  }
}

export async function runAllChecksOnce() {
  if (state.activePackJob) throw new Error("팩 빌드 진행 중에는 전체 테스트를 시작할 수 없습니다.");
  return withProblemTaskLock(async () => {
    const lease = acquireRunAllLease();
    if (!lease) throw new Error("이미 다른 탭에서 전체 테스트가 실행 중입니다.");
    updateGlobalActionState();
    try {
      await saveOpenFileIfDirty();
      return await runAllChecks();
    } finally {
      releaseRunAllLease(lease);
      updateGlobalActionState();
    }
  });
}

async function startPackBuild() {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  await saveOpenFileIfDirty();
  if (!hasFreshFullTest()) {
    throw new Error("팩 빌드 전 현재 문제의 전체 테스트를 먼저 통과해야 합니다.");
  }
  const problemId = state.selectedProblem;
  const packId = $("packIdInput").value.trim();
  const outputDir = PACK_OUTPUT_DIR;
  const verifyProfile = $("packVerifyProfileInput").value.trim() || "hidden";
  if (!packId) throw new Error("Pack ID를 입력하세요.");
  if (state.activePackJob) throw new Error("이미 팩 빌드가 진행 중입니다.");
  if (currentRunAllLock()) throw new Error("전체 테스트 진행 중에는 팩 빌드를 시작할 수 없습니다.");
  const job = await api(`/api/problems/${encodeURIComponent(problemId)}/packs/build`, {
    method: "POST",
    body: JSON.stringify({
      pack_id: packId,
      verify_profile: verifyProfile,
    }),
  });
  persistPackJob(job, problemId, { packId, outputDir });
  updateBuildPanel();
  showResult(`${problemId} 문제 팩 빌드를 백그라운드에서 시작했습니다.`, "summary success");
  schedulePackJobPoll(problemId, job.jobId, 500);
}

async function startPackBuildOnce() {
  return withProblemTaskLock(startPackBuild);
}

export async function buildPack() {
  $("packIdInput").value = $("packIdInput").value.trim() || "basic";
  $("packVerifyProfileInput").value = $("packVerifyProfileInput").value.trim() || "hidden";
  await saveOpenFileIfDirty();
  if (!hasFreshFullTest()) {
    showAlert("팩 빌드 전에 전체 테스트를 자동으로 실행합니다.", "info", {
      title: "팩 빌드 준비",
      timeout: 5000,
    });
    await runAllChecksOnce();
    if (!hasFreshFullTest()) {
      throw new Error("전체 테스트를 통과하지 못해 팩 빌드를 중단했습니다.");
    }
  }
  return startPackBuildOnce();
}
