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
  app.on("topAddProblemButton", "click", () => app.openModal("packModal"));
  app.on("problemJumpButton", "click", app.openProblemNavigation);
  app.on("cacheManageButton", "click", () => app.openModal("cacheModal"));
  app.on("refreshButton", "click", () => app.withErrors(app.refresh));
  app.on("modalBackdrop", "click", app.closeModals);
  for (const button of document.querySelectorAll("[data-modal-close]")) {
    button.addEventListener("click", app.closeModals);
  }
  app.on("debugModeInput", "change", app.renderDebugLog);
  app.on("problemSelect", "change", () => app.withErrors(async () => {
    await app.handleProblemChange();
    await app.refreshRecentSubmissions?.();
  }));
  app.on("problemSearchInput", "input", (event) => app.updateProblemSearch(event.target.value));
  app.on("problemPickerSearchInput", "input", (event) =>
    app.updateProblemSearch(event.target.value)
  );
  app.on("problemFolderMoveSelect", "change", (event) => {
    app.$("problemFolderMoveConfirmButton").disabled =
      event.target.value === event.target.dataset.currentFolder;
  });
  app.on("problemFolderMoveConfirmButton", "click", () =>
    app.withErrors(app.submitProblemFolderMove)
  );
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
    app.resetRunStatus(`${app.profileLabel(app.judgeProfile())} 테스트케이스를 채점에 사용합니다.`);
  });
  app.on("sourceFileInput", "change", () => app.withErrors(app.loadSourceFileIntoEditor));
  app.on("sourceHistoryFilterInput", "input", app.updateSourceHistoryFilter);
  app.on("sourceHistoryStatusFilter", "change", app.updateSourceHistoryFilter);
  app.on("sourceHistoryProblemScopeButton", "click", () => app.setSourceHistoryScope("problem"));
  app.on("sourceHistoryAllScopeButton", "click", () => app.setSourceHistoryScope("all"));
  app.on("filenameInput", "input", () => {
    app.saveProblemDraft?.(state.selectedProblem);
    app.updateLanguageBadge();
  });
  app.on("languageHint", "change", () => {
    app.saveProblemDraft?.(state.selectedProblem);
    app.syncFilenamePlaceholder();
    app.updateLanguageBadge();
  });
  app.on("sourceTextInput", "input", () => {
    app.saveProblemDraft?.(state.selectedProblem);
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
  app.on("defaultPackInstallButton", "click", () => app.withJobErrors(app.installDefaultPack));
  app.on("uploadPackButton", "click", () => app.withJobErrors(app.uploadPack));
  app.on("downloadPackButton", "click", () =>
    app.withJobErrors(() => app.downloadOfficialPack({ advanced: true }))
  );
  app.on("packRetryButton", "click", () => app.withJobErrors(app.retryPackInstall));
  app.on("packJobsButton", "click", app.viewPackJob);
  app.on("packFileInput", "change", app.updatePackActionState);
  app.on("casesCompileButton", "click", () => app.withJobErrors(app.compileCasesOnly));
  app.on("generateButton", "click", () => app.withJobErrors(app.generateData));
  app.on("sampleRunButton", "click", () => app.withJobErrors(() => app.runSubmission("sample")));
  app.on("fullRunButton", "click", () => app.withJobErrors(() => app.runSubmission("full")));
  app.on("runButton", "click", () => app.withJobErrors(() => app.runSubmission(app.judgeProfile())));
  app.on("lastResultButton", "click", () => {
    if (state.lastRunResult) app.showResultModal(state.lastRunResult);
  });
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
    const submissionArtifact = Boolean(target.closest("#submissionsDrawer"));
    const artifactRunId = submissionArtifact
      ? app.submissionArtifactRunId?.()
      : state.lastRunResult?.runId;
    if (caseArtifact && artifactRunId) {
      event.preventDefault();
      app.closeModals();
      void app.withErrors(() => app.loadWrongCase(artifactRunId, caseArtifact));
    }
  });
  app.on("cachePreviewButton", "click", () => app.withErrors(() => app.cacheClear(true, { all_entries: true })));
  app.on("cacheClearRunsButton", "click", () => app.withErrors(() => app.cacheClear(false, { runs: true })));
  app.on("cacheClearAllButton", "click", () => app.withErrors(() => app.cacheClear(false, { all_entries: true })));
  document.addEventListener("keydown", (event) => {
    if (app.handleModalKeydown?.(event)) return;
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
