/**
 * state 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

export const state = {
  workspace: null,
  repositories: [],
  activeRepository: null,
  repositoryMode: false,
  gitStatus: null,
  problems: [],
  selectedProblem: null,
  selectedFile: null,
  selectedTab: "info",
  detail: null,
  files: [],
  viewSeq: 0,
  loadingDepth: 0,
  lastSavedContent: "",
  lastSolutionVerification: null,
  lastSolutionStress: null,
  lastFullTest: null,
  lastPackResult: null,
  lastBulkBuildResult: null,
  lastRun: null,
  tabFeedbackById: {},
  dirtySolutionPaths: [],
  solutionTestResultsByPath: {},
  activeSolutionVerification: null,
  activeSolutionTestsByPath: {},
  lastStreamDetail: "",
  tabSelections: {},
  problemFolderCollapsed: {},
  resourceFilters: {},
  activeModalTrigger: null,
  activePackJob: null,
  activePackJobsByProblem: {},
  activeBulkJob: null,
  stalePackJob: null,
  stalePackJobsByProblem: {},
  packPollTimer: null,
  packPollTimersByProblem: {},
  editorMode: "default",
  editorSettingsOpen: false,
  vimMode: "insert",
  vimPending: "",
  vimOperatorCount: 1,
  vimCount: "",
  vimRegister: "",
  vimRegisterType: "char",
  vimPreferredColumn: null,
  vimVisualAnchor: null,
  vimVisualCursor: null,
  vimMessage: "",
  vimSearchQuery: "",
  vimSearchDirection: 1,
  editorUndoStack: [],
  editorRedoStack: [],
  editorCommandMode: "",
  codeMirror: null,
  modalEditors: {},
  editorApplyingValue: false,
  editorComposing: false,
  editorSnapshotBeforeIme: "",
  editingSolutionPath: null,
  solutionArtifactPreview: null,
  selectedSolutionArtifact: "input",
  stressMismatchPreview: null,
  selectedStressArtifact: "input",
  pendingStressAppend: null,
  codeMirrorPendingKey: "",
  progress: {
    active: false,
    title: "",
    steps: [],
    insightTitle: "현재 작업",
    insightBody: "",
  },
};

export const TAB_CONFIGS = {
  info: {
    title: "문제 정보",
    description: "문제 메타데이터를 수정하고 problem.json 원본을 함께 확인합니다.",
    files: ["problem.json"],
    actions: [
      { id: "saveMetadata", label: "문제 정보 저장", primary: true },
      { id: "openDeleteProblem", label: "문제 삭제", danger: true },
    ],
  },
  generator: {
    title: "데이터 생성",
    description: "cases.yml과 generator를 수정하고 sample/hidden 데이터를 생성합니다.",
    files: ["generator/cases.yml", "generator/generator.cpp"],
    actions: [
      { id: "compileCases", label: "Cases 검사", primary: true },
      { id: "compileGenerator", label: "Generator 컴파일" },
      { id: "generateSample", label: "Sample 데이터 생성" },
      { id: "generateHidden", label: "Hidden 데이터 생성" },
    ],
  },
  validator: {
    title: "데이터 벨리데이션",
    description: "validator를 수정하고 생성 데이터가 입력 조건을 만족하는지 확인합니다.",
    files: ["validator/validator.cpp"],
    actions: [
      { id: "compileValidator", label: "Validator 컴파일", primary: true },
      { id: "validateSample", label: "모든 데이터 생성+검증" },
    ],
  },
  checker: {
    title: "채점기",
    description: "checker와 기준 정답 코드를 수정하고 채점 도구를 컴파일합니다.",
    files: ["checker/judge.cpp", "solutions/main_solution.ac.cpp"],
    actions: [
      { id: "compileChecker", label: "Checker 컴파일", primary: true },
      { id: "compileReference", label: "기준 정답 컴파일" },
      { id: "compileTools", label: "전체 도구 컴파일" },
    ],
  },
  solutions: {
    title: "솔루션",
    description: "기대 결과 솔루션을 만들고 업로드한 뒤 hidden 데이터로 검증합니다.",
    files: [],
    actions: [
      { id: "newSolution", label: "새 솔루션 파일 만들기", primary: true },
      { id: "uploadSolutions", label: "솔루션 업로드" },
      { id: "verifySolutions", label: "기대 결과 검증" },
      { id: "stressSolutions", label: "Stress 테스트" },
    ],
  },
  build: {
    title: "검증/빌드",
    description: "현재 문제의 전체 테스트를 통과한 뒤 단일 문제 팩을 생성합니다.",
    files: [],
    actions: [
      { id: "runAllChecks", label: "전체 테스트", primary: true },
      { id: "buildPack", label: "검증 후 팩 빌드" },
    ],
  },
};

export const SAVE_BEFORE_ACTIONS = new Set([
  "compileCases",
  "compileGenerator",
  "generateSample",
  "generateHidden",
  "compileValidator",
  "validateSample",
  "compileChecker",
  "compileReference",
  "compileTools",
  "verifySolutions",
  "stressSolutions",
  "runAllChecks",
  "buildPack",
  "buildAllPacks",
]);

export const EXTENSIONS = {
  cpp: ".cpp",
  python: ".py",
  pypy: ".py",
  java: ".java",
};

export const LANGUAGE_BY_EXTENSION = {
  ".cpp": "cpp",
  ".cc": "cpp",
  ".cxx": "cpp",
  ".py": "python",
  ".java": "java",
};

export const EDITOR_INDENT = "    ";
export const STATUS_LABELS = {
  accepted: "AC",
  wrong_answer: "WA",
  time_limit: "TLE",
  memory_limit: "MLE",
  compile_error: "Compile Error",
  runtime_error: "Runtime Error",
  unknown: "Unknown",
};
export const EXPECTED_STATUS_BY_TOKEN = {
  ac: "accepted",
  wa: "wrong_answer",
  tle: "time_limit",
  mle: "memory_limit",
};
export const SAFE_PROBLEM_ID = /^[A-Za-z0-9_-]+$/;
export const SAFE_SOLUTION_NAME = /^[A-Za-z0-9_.-]+$/;
export const FILE_ROLES = {
  "problem.json": "문제 메타데이터",
  "generator/cases.yml": "케이스 정의",
  "generator/generator.cpp": "입력 생성기",
  "validator/validator.cpp": "입력 검증기",
  "checker/judge.cpp": "정답 비교기",
  "solutions/main_solution.ac.cpp": "기준 정답",
};
export const PERSISTED_VIEW_KEY = "problem-studio:view:v1";
export const RUN_ALL_LOCK_KEY = "problem-studio:run-all-lock:v1";
export const PACK_JOB_KEY = "problem-studio:pack-job:v1";
export const LAST_RESULTS_KEY = "problem-studio:last-results:v1";
export const EDITOR_SETTINGS_KEY = "problem-studio:editor-settings:v1";
export const DELETE_CONFIRM_PHRASE = "확인했습니다";
export const METADATA_TIMEOUT_FIELDS = [
  ["metadataCompileTimeout", "compileTimeoutMs", "컴파일 제한"],
  ["metadataGenerationTimeout", "generationTimeoutMs", "데이터 생성 제한"],
  ["metadataSolutionTimeout", "solutionTimeoutMs", "기준 정답 제한"],
  ["metadataUserTimeout", "userTimeoutMs", "사용자 코드 제한"],
];
export const METADATA_MEMORY_FIELDS = [
  ["metadataUserMemoryLimit", "userMemoryLimitMb", "사용자 코드 메모리 제한"],
];
export const METADATA_TOOL_FIELDS = [
  ["metadataToolGenerator", "generator", "Generator"],
  ["metadataToolGeneratorConfig", "generatorConfig", "Cases YAML"],
  ["metadataToolValidator", "validator", "Validator"],
  ["metadataToolChecker", "checker", "Checker"],
  ["metadataToolSolution", "solution", "기준 정답"],
];
export const RUN_ALL_LOCK_TTL_MS = 60 * 60 * 1000;
export const PROBLEM_TASK_LOCK_NAME = "problem-studio-problem-task";
export const PACK_OUTPUT_DIR = "dist/packs";
export const EDITOR_HISTORY_LIMIT = 120;
export const TAB_INSTANCE_ID =
  window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
export const runAllChannel =
  "BroadcastChannel" in window ? new BroadcastChannel("problem-studio-run-all") : null;
export function activeRepositoryKey() {
  return state.activeRepository || "legacy";
}
export function problemStateKey(
  problemId = state.selectedProblem,
  repositoryName = state.activeRepository || null
) {
  return problemId ? `${repositoryName || "legacy"}:${problemId}` : "";
}
export function activePackJobForProblem(
  problemId = state.selectedProblem,
  repositoryName = state.activeRepository || null
) {
  const key = problemStateKey(problemId, repositoryName);
  return key ? state.activePackJobsByProblem?.[key] || null : null;
}
export function activePackJobList(repositoryName = state.activeRepository || null) {
  return Object.values(state.activePackJobsByProblem || {}).filter(
    (job) => (job.repositoryName || null) === (repositoryName || null)
  );
}
export function stalePackJobForProblem(
  problemId = state.selectedProblem,
  repositoryName = state.activeRepository || null
) {
  const key = problemStateKey(problemId, repositoryName);
  return key ? state.stalePackJobsByProblem?.[key] || null : null;
}
export function stalePackJobList(repositoryName = state.activeRepository || null) {
  return Object.values(state.stalePackJobsByProblem || {}).filter(
    (job) => (job.repositoryName || null) === (repositoryName || null)
  );
}
