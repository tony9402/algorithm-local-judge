/**
 * build 화면 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { optional, setText } from "./dom.js";
import { currentProblemResult, hasFreshFullTest } from "./results.js";
import { PACK_OUTPUT_DIR, state } from "./state.js";
import { updateEditorPanelMode } from "./tabs-view.js";

const buildCallbacks = {
  formatTime: () => "",
  packJobSummary: () => "",
};
export function configureBuildView(callbacks = {}) {
  Object.assign(buildCallbacks, callbacks);
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
  const profile = optional("packVerifyProfileInput")?.value.trim() || "hidden";
  let tone = "neutral";
  let title = "전체 테스트 필요";
  let summary = "팩 빌드 전에 현재 문제의 전체 테스트를 실행해야 합니다.";
  let testState = "대기";
  let testDetail = "아직 통과 기록이 없습니다.";

  if (state.activePackJob) {
    tone = "running";
    title = "팩 빌드 진행 중";
    summary = buildCallbacks.packJobSummary(state.activePackJob);
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
    state.activePackJob ? buildCallbacks.packJobSummary(state.activePackJob) : pack?.archiveLabel || "아직 없음"
  );
  updateDownloadLink(optional("buildDashboardDownloadLink"), pack, "팩 파일");
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
  const status = optional("buildValidationStatus");
  const output = optional("packOutputLabel");
  const link = optional("packDownloadLink");
  if (output) output.textContent = PACK_OUTPUT_DIR;
  if (status) {
    if (state.activePackJob) {
      status.textContent = `팩 빌드 진행 중입니다. ${buildCallbacks.packJobSummary(state.activePackJob)}`;
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
}
