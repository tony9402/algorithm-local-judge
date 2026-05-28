const app = window.AljApp;
const { state } = app;

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
