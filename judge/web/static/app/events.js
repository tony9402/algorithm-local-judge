/**
 * events 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;
/**
 * events 이벤트를 DOM 요소와 핸들러에 연결합니다.
 */
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
    app.withErrors(app.createProblemFolderFromInput)
  );
  app.on("problemFolderInput", "input", app.renderProblemSelection);
  app.on("problemFolderInput", "keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void app.withErrors(app.createProblemFolderFromInput);
    }
  });
  app.on("runProfileSelect", "change", () => {
    state.config.judgeProfile = app.$("runProfileSelect").value;
    app.resetRunStatus(`${app.judgeProfile()} cases will be used for Run.`);
  });
  app.on("sourceFileInput", "change", () => app.withErrors(app.loadSourceFileIntoEditor));
  app.on("sourceHistoryFilterInput", "input", app.updateSourceHistoryFilter);
  app.on("sourceHistoryStatusFilter", "change", app.updateSourceHistoryFilter);
  app.on("filenameInput", "input", app.updateLanguageBadge);
  app.on("languageHint", "change", () => {
    app.syncFilenamePlaceholder();
    app.updateLanguageBadge();
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
  app.on("sampleRunButton", "click", () => app.withJobErrors(() => app.runSubmission("sample")));
  app.on("fullRunButton", "click", () => app.withJobErrors(() => app.runSubmission("full")));
  app.on("runButton", "click", () => app.withJobErrors(() => app.runSubmission(app.judgeProfile())));
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const toggleFolder = target.closest("[data-folder-toggle]")?.getAttribute("data-folder-toggle");
    if (toggleFolder !== null && toggleFolder !== undefined) {
      event.preventDefault();
      app.toggleFolderCollapsed(toggleFolder);
      return;
    }
    const deleteFolder = target.closest("[data-folder-delete]")?.getAttribute("data-folder-delete");
    if (deleteFolder) {
      event.preventDefault();
      void app.withErrors(() => app.deleteProblemFolder(deleteFolder));
      return;
    }
    const caseArtifact = target.closest("[data-case-artifact]")?.getAttribute("data-case-artifact");
    if (caseArtifact && state.lastRunResult?.runId) {
      event.preventDefault();
      app.closeModals();
      void app.withErrors(() => app.loadWrongCase(state.lastRunResult.runId, caseArtifact));
    }
  });
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
