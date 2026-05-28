/**
 * state 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

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
function sampleProfile() {
  return state.config?.sampleProfile || "sample";
}
function judgeProfile() {
  const selector = document.getElementById("runProfileSelect");
  return selector?.value || state.config?.judgeProfile || "full";
}

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
