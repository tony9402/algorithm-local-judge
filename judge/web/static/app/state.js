const state = {
  problems: [],
  selectedProblem: null,
  sourceMode: "upload",
  artifacts: null,
  selectedArtifact: "input",
  artifactExpanded: false,
  artifactWrap: false,
  cache: null,
  sources: [],
  sourceHistoryFilter: "",
  sourceHistoryStatusFilter: "all",
  debugLogs: [],
  generationProgress: { current: 0, total: 0 },
  sampleLoadToken: 0,
  sampleCache: {},
  isBusy: false,
  config: {
    sampleProfile: "sample",
    judgeProfile: "full",
    webDebug: false,
  },
};

const SELECTED_PROBLEM_KEY = "alj:selected-problem:v1";

/**
 * sampleProfile 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function sampleProfile() {
  return state.config?.sampleProfile || "sample";
}

/**
 * judgeProfile 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function judgeProfile() {
  const selector = document.getElementById("runProfileSelect");
  return selector?.value || state.config?.judgeProfile || "full";
}

/**
 * profileCaseText 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} count `count` 값입니다.
 * @param {any} profile `profile` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function profileCaseText(count, profile = judgeProfile()) {
  return `${count} ${profile} case(s)`;
}

window.AljApp = {
  ARTIFACT_PREVIEW_LIMIT: 12000,
  SELECTED_PROBLEM_KEY,
  judgeProfile,
  profileCaseText,
  sampleProfile,
  state,
};
