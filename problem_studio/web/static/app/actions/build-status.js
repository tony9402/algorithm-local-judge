import { escapeHtml, optional } from "../dom.js";
import { TAB_INSTANCE_ID, state } from "../state.js";
import { currentRunAllLock } from "./build-locks.js";

/**
 * formatTime 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function formatTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * packJobSummary 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} job `job` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function packJobSummary(job) {
  if (!job) return "";
  return [
    job.problemId ? `${job.problemId} 문제` : "",
    job.packId ? `Pack ${job.packId}` : "",
    job.outputDir || "",
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * updateRunAllButton 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function updateRunAllButton() {
  const button = optional("runAllButton");
  if (!button) return;
  const lock = currentRunAllLock();
  const lockedByAnotherTab = Boolean(lock && lock.owner !== TAB_INSTANCE_ID);
  const packActive = Boolean(state.activePackJob);
  const bulkActive = Boolean(state.activeBulkJob);
  const bulkCancelling = state.activeBulkJob?.status === "cancelling" || state.activeBulkJob?.cancelRequested;
  button.disabled =
    lockedByAnotherTab
    || packActive
    || bulkActive
    || document.body.getAttribute("aria-busy") === "true";
  button.textContent = packActive
    ? "팩 빌드 진행 중"
    : bulkActive
      ? bulkCancelling ? "전체 빌드 취소 중" : "전체 문제 빌드 중"
      : lockedByAnotherTab
        ? "전체 테스트 진행 중"
        : "전체 테스트";
  button.title = packActive
    ? packJobSummary(state.activePackJob)
    : lockedByAnotherTab
      ? `${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)} 시작`
      : "";
}

/**
 * updatePackButton 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function updatePackButton() {
  const button = optional("packButton");
  if (!button) return;
  const active = Boolean(state.activePackJob);
  const bulkActive = Boolean(state.activeBulkJob);
  const bulkCancelling = state.activeBulkJob?.status === "cancelling" || state.activeBulkJob?.cancelRequested;
  const lock = currentRunAllLock();
  const runAllActive = Boolean(lock);
  button.disabled =
    active || bulkActive || runAllActive || document.body.getAttribute("aria-busy") === "true";
  button.textContent = active
    ? "팩 빌드 중"
    : bulkActive
      ? bulkCancelling ? "전체 빌드 취소 중" : "전체 문제 빌드 중"
      : runAllActive
        ? "전체 테스트 진행 중"
        : "팩 빌드";
  button.title = active
    ? packJobSummary(state.activePackJob)
    : bulkActive
      ? state.activeBulkJob.title || "전체 문제 테스트/팩 빌드"
      : runAllActive
        ? `${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)} 시작`
        : "";
}

/**
 * bulkProblemIds 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function bulkProblemIds() {
  return (state.problems || []).map((problem) => problem.problemId).filter(Boolean);
}

/**
 * selectedBulkProblemIdsFromModal 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function selectedBulkProblemIdsFromModal() {
  return Array.from(document.querySelectorAll("[data-bulk-problem]:checked"))
    .map((input) => input.value)
    .filter(Boolean);
}

/**
 * bulkMaxWorkersFromModal 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function bulkMaxWorkersFromModal() {
  const value = Number.parseInt(optional("bulkMaxWorkersInput")?.value || "", 10);
  return Number.isFinite(value) && value > 0 ? value : null;
}

/**
 * updateBulkStartButton 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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
  button.disabled = selectedCount === 0 || document.body.getAttribute("aria-busy") === "true";
  button.textContent = selectedCount
    ? `선택한 ${selectedCount}개 문제로 팩 빌드`
    : "문제를 선택하세요";
}

/**
 * bulkBuildButtons 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function bulkBuildButtons() {
  return [optional("workspaceBuildAllButton"), optional("buildAllPacksButton")].filter(Boolean);
}

/**
 * updateBuildAllPacksButton 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function updateBuildAllPacksButton() {
  const buttons = bulkBuildButtons();
  if (!buttons.length) return;
  const active = Boolean(state.activePackJob);
  const bulkActive = Boolean(state.activeBulkJob);
  const bulkCancelling = state.activeBulkJob?.status === "cancelling" || state.activeBulkJob?.cancelRequested;
  const lock = currentRunAllLock();
  const runAllActive = Boolean(lock);
  const hasProblems = bulkProblemIds().length > 0;
  for (const button of buttons) {
    button.disabled =
      !hasProblems
      || active
      || bulkActive
      || runAllActive
      || document.body.getAttribute("aria-busy") === "true";
    button.textContent = active
      ? "팩 빌드 진행 중"
      : bulkActive
        ? bulkCancelling ? "전체 빌드 취소 중" : "전체 문제 빌드 중"
        : runAllActive
          ? "전체 테스트 진행 중"
          : "전체 문제 테스트/팩 빌드";
    button.title = !hasProblems
      ? "등록된 문제가 없습니다."
      : active
        ? packJobSummary(state.activePackJob)
        : bulkActive
          ? state.activeBulkJob.title || "전체 문제 테스트/팩 빌드"
          : runAllActive
            ? `${lock.problemId || "전체 문제"} · ${formatTime(lock.startedAt)} 시작`
            : "모든 문제를 순서대로 테스트하고 통과한 문제 팩을 생성합니다.";
  }
}

/**
 * updateGlobalStatus 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function updateGlobalStatus() {
  const status = optional("globalTaskStatus");
  if (!status) return;
  const lock = currentRunAllLock();
  const messages = [];
  if (lock) {
    messages.push({
      text: `전체 테스트 진행 중 · ${lock.problemId || "다른 문제"} · ${formatTime(lock.startedAt)}`,
    });
  }
  if (state.activePackJob) {
    const summary = escapeHtml(packJobSummary(state.activePackJob));
    messages.push({
      html:
        `팩 빌드 진행 중 · ${summary} ` +
        `<button type="button" data-cancel-pack-job>취소</button>`,
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
  if (state.stalePackJob) {
    const staleSummary = escapeHtml(packJobSummary(state.stalePackJob));
    messages.push({
      html:
        `만료된 팩 빌드 · ${staleSummary} ` +
        `<button type="button" data-dismiss-stale-pack-job>닫기</button>`,
    });
  }
  status.innerHTML = messages
    .map((message) => message.html || escapeHtml(message.text || ""))
    .join(" / ");
  status.classList.toggle("hidden", !messages.length);
}

/**
 * updateGlobalActionState 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function updateGlobalActionState() {
  updateRunAllButton();
  updatePackButton();
  updateBuildAllPacksButton();
  updateGlobalStatus();
}
