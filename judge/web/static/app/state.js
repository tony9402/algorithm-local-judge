/**
 * state 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const state = {
  problems: [],
  folders: [],
  selectedProblem: null,
  sourceMode: "text",
  artifacts: null,
  selectedArtifact: "input",
  artifactExpanded: false,
  artifactWrap: false,
  cache: null,
  sources: [],
  sourceHistoryFilter: "",
  sourceHistoryScope: "problem",
  sourceHistoryStatusFilter: "all",
  debugLogs: [],
  generationProgress: { current: 0, total: 0 },
  sampleLoadToken: 0,
  sampleCache: {},
  submissionCooldowns: {},
  cooldownTimer: null,
  jobsPage: 1,
  jobsPageSize: 5,
  jobsFilter: "all",
  jobsTotal: 0,
  jobsTotalPages: 1,
  jobsServerPaged: false,
  isBusy: false,
  pendingJobAction: false,
  problemDrafts: {},
  config: {
    sampleProfile: "sample",
    judgeProfile: "full",
    webDebug: false,
  },
};

const SELECTED_PROBLEM_KEY = "alj:selected-problem:v1";
const COLLAPSED_FOLDERS_KEY = "alj:collapsed-folders:v1";
function sampleProfile() {
  return state.config?.sampleProfile || "sample";
}
function judgeProfile() {
  const selector = document.getElementById("runProfileSelect");
  return selector?.value || state.config?.judgeProfile || "full";
}

function profileCaseText(count, profile = judgeProfile()) {
  return `${count}개 ${profile} 케이스`;
}

window.AljApp = {
  ARTIFACT_PREVIEW_LIMIT: 12000,
  COLLAPSED_FOLDERS_KEY,
  SELECTED_PROBLEM_KEY,
  judgeProfile,
  profileCaseText,
  sampleProfile,
  state,
};
