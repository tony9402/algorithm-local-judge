/**
 * refresh 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;
/**
 * 데이터 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 */
async function refresh() {
  app.setText("subtitle", "Connecting to local server");
  const [config, problems] = await Promise.all([app.api("/api/config"), app.api("/api/problems")]);
  state.config = { ...state.config, ...config };
  app.renderProblems(problems);
  app.configureDebugUi();
  const officialRepoInput = app.optional("officialRepoInput");
  if (officialRepoInput) {
    officialRepoInput.value = state.config?.officialRepository || "tony9402/algorithm-package";
  }
  app.setText("subtitle", "Connected to local server");
  const samplePromise = state.selectedProblem ? app.loadSamples() : Promise.resolve();
  const secondaryPromise = refreshSecondaryData();
  await samplePromise;
  await secondaryPromise;
}
/**
 * secondary 데이터 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 */
async function refreshSecondaryData() {
  try {
    const [packs, cache, sources] = await Promise.all([
      app.api("/api/packs"),
      app.api("/api/cache"),
      app.api("/api/sources"),
    ]);
    app.renderPacks(packs);
    app.renderCache(cache);
    app.renderSourceHistory(sources);
  } catch (error) {
    app.showError(error.message);
  }
}

Object.assign(app, {
  refresh,
  refreshSecondaryData,
});
