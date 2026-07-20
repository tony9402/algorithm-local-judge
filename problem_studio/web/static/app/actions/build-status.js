/**
 * build 상태 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { escapeHtml, optional } from "../dom.js";
import { bindControlPolicy } from "../control-policy.js";
import {
  TAB_INSTANCE_ID,
  activePackJobForProblem,
  activePackJobList,
  stalePackJobList,
  state,
} from "../state.js";
import { allRunAllLocks, currentRunAllLock } from "./build-locks.js";
import { currentProblemResult, hasFreshFullTest } from "../results.js";
export function formatTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}
export function packJobSummary(job) {
  if (!job) return "";
  return [
    job.problemId ? `${job.problemId} 문제` : "",
    job.packId ? `팩 ${job.packId}` : "",
    job.outputDir || "",
  ]
    .filter(Boolean)
    .join(" · ");
}
/**
 * 실행 all button 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updateRunAllButton() {
  const button = optional("runAllButton");
  if (!button) return;
  const lock = currentRunAllLock();
  const lockedByAnotherTab = Boolean(lock && lock.owner !== TAB_INSTANCE_ID);
  const activePackJob = activePackJobForProblem();
  const packActive = Boolean(activePackJob);
  const bulkActive = Boolean(state.activeBulkJob);
  const bulkCancelling = state.activeBulkJob?.status === "cancelling" || state.activeBulkJob?.cancelRequested;
  button.textContent = packActive
    ? "팩 빌드 진행 중"
    : bulkActive
      ? bulkCancelling ? "전체 빌드 취소 중" : "전체 문제 빌드 중"
      : lockedByAnotherTab
        ? "전체 테스트 진행 중"
        : "전체 테스트";
  const enabledTitle = packActive
    ? packJobSummary(activePackJob)
    : lockedByAnotherTab
      ? `${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)} 시작`
      : "";
  bindControlPolicy(button, "build.run-all", {
    context: () => ({
      bulkActive,
      bulkReason: state.activeBulkJob?.title || "전체 문제 테스트/팩 빌드",
      lockedByAnotherTab,
      packActive,
      packReason: packJobSummary(activePackJob),
      runAllReason: lock
        ? `${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)} 시작`
        : "",
    }),
    enabledTitle,
  });
}
/**
 * 문제팩 button 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updatePackButton() {
  const button = optional("packButton");
  if (!button) return;
  const activePackJob = activePackJobForProblem();
  const active = Boolean(activePackJob);
  const bulkActive = Boolean(state.activeBulkJob);
  const bulkCancelling = state.activeBulkJob?.status === "cancelling" || state.activeBulkJob?.cancelRequested;
  const lock = currentRunAllLock();
  const runAllActive = Boolean(lock);
  const result = currentProblemResult();
  const hasAttemptedFullTest = Boolean(result?.fullTest || state.lastFullTest);
  const packPrerequisiteMissing = Boolean(
    state.selectedProblem
      && hasAttemptedFullTest
      && (result?.dirtyAfterFullTest || !hasFreshFullTest())
  );
  button.textContent = active
    ? "팩 빌드 중"
    : bulkActive
      ? bulkCancelling ? "전체 빌드 취소 중" : "전체 문제 빌드 중"
      : runAllActive
        ? "전체 테스트 진행 중"
        : "팩 빌드";
  const enabledTitle = active
    ? packJobSummary(activePackJob)
    : bulkActive
      ? state.activeBulkJob.title || "전체 문제 테스트/팩 빌드"
      : runAllActive
        ? `${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)} 시작`
        : "";
  bindControlPolicy(button, "build.pack", {
    context: () => ({
      bulkActive,
      bulkReason: state.activeBulkJob?.title || "전체 문제 테스트/팩 빌드",
      packActive: active,
      packReason: packJobSummary(activePackJob),
      packPrerequisiteMissing,
      packPrerequisiteReason: result?.dirtyAfterFullTest
        ? (result.dirtyReason || "변경사항이 있어 전체 테스트를 다시 실행해야 합니다.")
        : "전체 테스트를 통과한 뒤 팩을 빌드할 수 있습니다.",
      runAllActive,
      runAllReason: lock
        ? `${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)} 시작`
        : "",
    }),
    enabledTitle,
  });
}
export function bulkProblemIds() {
  return (state.problems || []).map((problem) => problem.problemId).filter(Boolean);
}
export function selectedBulkProblemIdsFromModal() {
  const serialized = optional("bulkProblemList")?.dataset.selectedProblemIds;
  if (serialized) {
    try {
      const selected = JSON.parse(serialized);
      if (Array.isArray(selected)) return selected.filter(Boolean);
    } catch {
      // 이전 DOM 계약으로 계속 읽습니다.
    }
  }
  return Array.from(document.querySelectorAll("[data-bulk-problem]:checked"))
    .map((input) => input.value)
    .filter(Boolean);
}
export function bulkMaxWorkersFromModal() {
  const value = Number.parseInt(optional("bulkMaxWorkersInput")?.value || "", 10);
  return Number.isFinite(value) && value > 0 ? value : null;
}
/**
 * 일괄 작업 start button 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
export function updateBulkStartButton() {
  const button = optional("workspaceBuildStartButton");
  if (!button) return;
  const selectedCount = selectedBulkProblemIdsFromModal().length;
  const totalCount = bulkProblemIds().length;
  const summary = optional("bulkBuildSummary");
  const workers = bulkMaxWorkersFromModal();
  if (summary) {
    summary.textContent = selectedCount
      ? `${totalCount}개 중 ${selectedCount}개 문제 선택 · ${workers ? `${workers}개 워커` : "워커 자동"}`
      : "팩에 포함할 문제를 하나 이상 선택하세요.";
  }
  button.textContent = selectedCount
    ? `선택한 ${selectedCount}개 문제로 팩 빌드`
    : "문제를 선택하세요";
  bindControlPolicy(button, "build.bulk-start", {
    context: () => ({ selectedCount }),
  });
}

function bulkBuildButtons() {
  return [optional("workspaceBuildAllButton"), optional("buildAllPacksButton")].filter(Boolean);
}
/**
 * build all 문제팩 button 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updateBuildAllPacksButton() {
  const buttons = bulkBuildButtons();
  if (!buttons.length) return;
  const activePackJobs = activePackJobList();
  const active = activePackJobs.length > 0;
  const bulkActive = Boolean(state.activeBulkJob);
  const bulkCancelling = state.activeBulkJob?.status === "cancelling" || state.activeBulkJob?.cancelRequested;
  const locks = allRunAllLocks();
  const runAllActive = locks.length > 0;
  const hasProblems = bulkProblemIds().length > 0;
  for (const button of buttons) {
    button.textContent = active
      ? "팩 빌드 진행 중"
      : bulkActive
        ? bulkCancelling ? "전체 빌드 취소 중" : "전체 문제 빌드 중"
        : runAllActive
          ? "전체 테스트 진행 중"
          : "전체 문제 테스트/팩 빌드";
    const enabledTitle = !hasProblems
      ? "등록된 문제가 없습니다."
      : active
        ? activePackJobs.map(packJobSummary).filter(Boolean).join(" / ")
        : bulkActive
          ? state.activeBulkJob.title || "전체 문제 테스트/팩 빌드"
          : runAllActive
            ? locks.map((lock) => `${lock.problemId || "전체 문제"} · ${formatTime(lock.startedAt)} 시작`).join(" / ")
            : "모든 문제를 순서대로 테스트하고 통과한 문제 팩을 생성합니다.";
    bindControlPolicy(button, "build.bulk-all", {
      context: () => ({
        bulkActive,
        bulkReason: state.activeBulkJob?.title || "전체 문제 테스트/팩 빌드",
        hasProblems,
        packActive: active,
        packReason: activePackJobs.map(packJobSummary).filter(Boolean).join(" / "),
        runAllActive,
        runAllReason: locks
          .map((lock) => `${lock.problemId || "전체 문제"} · ${formatTime(lock.startedAt)} 시작`)
          .join(" / "),
      }),
      enabledTitle,
    });
  }
}
function repositoryDataAttribute(repositoryName) {
  return `data-pack-repository="${escapeHtml(repositoryName || "")}"`;
}
/**
 * global 상태 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updateGlobalStatus() {
  const status = optional("globalTaskStatus");
  if (!status) return;
  const locks = allRunAllLocks();
  const messages = [];
  for (const lock of locks) {
    messages.push({
      text: `전체 테스트 진행 중 · ${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)}`,
    });
  }
  for (const job of activePackJobList()) {
    const summary = escapeHtml(packJobSummary(job));
    messages.push({
      html:
        `팩 빌드 진행 중 · ${summary} ` +
        `<button type="button" data-cancel-pack-job="${escapeHtml(job.problemId || "")}" ${repositoryDataAttribute(job.repositoryName)}>취소</button>`,
    });
  }
  if (state.activeBulkJob) {
    const bulkCancelling = state.activeBulkJob.status === "cancelling" || state.activeBulkJob.cancelRequested;
    messages.push({
      html: bulkCancelling
        ? `전체 문제 빌드 취소 중 · ${escapeHtml(state.activeBulkJob.title || "workspace")}`
        : (
            `전체 문제 빌드 진행 중 · ${escapeHtml(state.activeBulkJob.title || "workspace")} ` +
            `<button type="button" data-cancel-bulk-job>취소</button>`
          ),
    });
  }
  for (const job of stalePackJobList()) {
    const staleSummary = escapeHtml(packJobSummary(job));
    messages.push({
      html:
        `만료된 팩 빌드 · ${staleSummary} ` +
        `<button type="button" data-dismiss-stale-pack-job="${escapeHtml(job.problemId || "")}" ${repositoryDataAttribute(job.repositoryName)}>닫기</button>`,
    });
  }
  status.innerHTML = messages
    .map((message) => message.html || escapeHtml(message.text || ""))
    .join(" / ");
  status.classList.toggle("hidden", !messages.length);
}
/**
 * global action state 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
export function updateGlobalActionState() {
  updateRunAllButton();
  updatePackButton();
  updateBuildAllPacksButton();
  updateGlobalStatus();
}
