const app = window.AljApp;
const { state } = app;

/**
 * refresh 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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
 * refreshSecondaryData 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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
