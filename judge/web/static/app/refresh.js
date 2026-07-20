/**
 * refresh 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;
/**
 * 데이터 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 */
async function refresh() {
  const attemptToken = ++state.connectionAttemptToken;
  app.setText("subtitle", "로컬 서버에 연결하는 중");
  app.setConnectionPending();
  try {
    const [config, problems, folders] = await Promise.all([
      app.api("/api/config"),
      app.api("/api/problems"),
      app.api("/api/folders"),
    ]);
    if (attemptToken !== state.connectionAttemptToken) return;
    state.config = { ...state.config, ...config };
    state.folders = folders || [];
    app.renderProblems(problems);
    app.configureDebugUi();
    const officialRepoInput = app.optional("officialRepoInput");
    if (officialRepoInput) {
      officialRepoInput.value = state.config?.officialRepository || "tony9402/algorithm-package";
    }
    app.setText("subtitle", "로컬 서버에 연결됨");
    app.setConnectionConnected();
    const samplePromise = state.selectedProblem ? app.loadSamples() : Promise.resolve();
    const secondaryPromise = refreshSecondaryData();
    await samplePromise;
    await secondaryPromise;
  } catch (error) {
    if (attemptToken !== state.connectionAttemptToken) return;
    app.setText("subtitle", "로컬 서버 연결 실패");
    app.showConnectionError(error);
    throw error;
  }
}
/**
 * secondary 데이터 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 */
async function refreshSecondaryData() {
  const regions = [
    ["packs", async () => app.renderPacks(await app.api("/api/packs"))],
    ["cache", async () => app.renderCache(await app.api("/api/cache"))],
    ["sources", async () => app.renderSourceHistory(await app.api("/api/sources"))],
  ];
  if (app.refreshRecentSubmissions) {
    regions.push(["recent-submissions", app.refreshRecentSubmissions]);
  }
  if (
    app.refreshSubmissions &&
    !app.optional("submissionsDrawer")?.classList.contains("hidden")
  ) {
    regions.push(["submissions", app.refreshSubmissions]);
  }
  const results = await Promise.allSettled(regions.map(([, action]) => action()));
  results.forEach((result, index) => {
    const [region] = regions[index];
    if (result.status === "fulfilled") {
      app.clearSecondaryError(region);
      return;
    }
    app.showSecondaryError(region, result.reason);
  });
  return Object.fromEntries(
    results.map((result, index) => [regions[index][0], result.status])
  );
}

async function refreshSecondaryRegion(region) {
  const actions = {
    packs: async () => app.renderPacks(await app.api("/api/packs")),
    cache: async () => app.renderCache(await app.api("/api/cache")),
    sources: async () => app.renderSourceHistory(await app.api("/api/sources")),
    "recent-submissions": app.refreshRecentSubmissions,
    submissions: app.refreshSubmissions,
  };
  const action = actions[region];
  if (!action) return;
  try {
    await action();
    app.clearSecondaryError(region);
  } catch (error) {
    app.showSecondaryError(region, error);
  }
}

Object.assign(app, {
  refresh,
  refreshSecondaryData,
  refreshSecondaryRegion,
});
