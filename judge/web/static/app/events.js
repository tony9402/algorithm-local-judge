const app = window.AljApp;
const { state } = app;

function bindEvents() {
  app.applyTheme(app.preferredTheme());
  app.on("themeToggleButton", "click", app.toggleTheme);
  app.on("addProblemButton", "click", () => app.openModal("packModal"));
  app.on("cacheManageButton", "click", () => app.openModal("cacheModal"));
  app.on("refreshButton", "click", () => app.withErrors(app.refresh));
  app.on("modalBackdrop", "click", app.closeModals);
  for (const button of document.querySelectorAll("[data-modal-close]")) {
    button.addEventListener("click", app.closeModals);
  }
  app.on("debugModeInput", "change", app.renderDebugLog);
  app.on("problemSelect", "change", () => app.withErrors(app.handleProblemChange));
  app.on("problemFolderSaveButton", "click", () =>
    app.withErrors(app.updateSelectedProblemFolder)
  );
  app.on("problemFolderInput", "keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void app.withErrors(app.updateSelectedProblemFolder);
    }
  });
  app.on("runProfileSelect", "change", () => {
    state.config.judgeProfile = app.$("runProfileSelect").value;
    app.resetRunStatus(`${app.judgeProfile()} cases will be used for Run.`);
  });
  app.on("sourceFileInput", "change", app.updateLanguageBadge);
  app.on("sourceHistoryFilterInput", "input", app.updateSourceHistoryFilter);
  app.on("sourceHistoryStatusFilter", "change", app.updateSourceHistoryFilter);
  app.on("filenameInput", "input", app.updateLanguageBadge);
  app.on("languageHint", "change", () => {
    app.syncFilenamePlaceholder();
    if (!app.$("filenameInput").value.trim()) app.updateLanguageBadge();
  });
  app.on("sourceTextInput", "input", () => {
    app.updateEditorView();
    app.updateActionState();
  });
  app.on("sourceTextInput", "scroll", app.syncEditorScroll);
  const sourceTextInput = app.optional("sourceTextInput");
  if (sourceTextInput) {
    sourceTextInput.addEventListener("keydown", (event) => {
      if (event.key === "Tab") {
        event.preventDefault();
        app.insertEditorText("  ");
      }
    });
  }
  app.on("uploadModeButton", "click", () => app.setMode("upload"));
  app.on("textModeButton", "click", () => app.setMode("text"));
  app.on("uploadPackButton", "click", () => app.withJobErrors(app.uploadPack));
  app.on("downloadPackButton", "click", () => app.withJobErrors(app.downloadOfficialPack));
  app.on("packFileInput", "change", app.updatePackActionState);
  app.on("casesCompileButton", "click", () => app.withJobErrors(app.compileCasesOnly));
  app.on("generateButton", "click", () => app.withJobErrors(app.generateData));
  app.on("runButton", "click", () => app.withJobErrors(app.runSubmission));
  app.on("cachePreviewButton", "click", () => app.withErrors(() => app.cacheClear(true, { all_entries: true })));
  app.on("cacheClearRunsButton", "click", () => app.withErrors(() => app.cacheClear(false, { runs: true })));
  app.on("cacheClearAllButton", "click", () => app.withErrors(() => app.cacheClear(false, { all_entries: true })));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") app.closeModals();
  });
  for (const button of document.querySelectorAll(".artifact-tab")) {
    button.addEventListener("click", () => {
      state.selectedArtifact = button.dataset.artifact;
      state.artifactExpanded = false;
      app.renderArtifact();
    });
  }
  app.on("artifactCopyButton", "click", () => app.withErrors(app.copyArtifact));
  app.on("artifactDownloadButton", "click", app.downloadArtifact);
  app.on("artifactWrapButton", "click", app.toggleArtifactWrap);
  app.on("artifactExpandButton", "click", app.toggleArtifactExpanded);
  app.bindDropZone();
  app.syncFilenamePlaceholder();
  app.updateEditorView();
  app.updateActionState();
  app.updatePackActionState();
}

Object.assign(app, {
  bindEvents,
});
