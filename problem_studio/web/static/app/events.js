/**
 * events 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { $, optional } from "./dom.js";
import { activeCodeEditorElement } from "./modal.js";
import { LAST_RESULTS_STORAGE_KEY } from "./results.js";
import {
  PACK_JOB_KEY,
  RUN_ALL_LOCK_KEY,
  runAllChannel,
  state,
} from "./state.js";
/**
 * 애플리케이션 events 이벤트를 DOM 요소와 핸들러에 연결합니다.
 *
 * @param {Array} actions 애플리케이션 events을 계산하거나 검증할 때 필요한 actions 입력입니다.
 */
export function bindAppEvents(actions) {
  actions.bindEditorEvents();
  optional("editorCommandInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      actions.closeEditorCommandLine();
      actions.focusEditor();
    }
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      actions.submitEditorCommandLine();
    }
  });
  $("editorSettingsButton").addEventListener("click", (event) => {
    event.stopPropagation();
    actions.setEditorSettingsOpen(!state.editorSettingsOpen);
  });
  $("editorSettingsPanel").addEventListener("click", (event) => {
    event.stopPropagation();
  });
  for (const button of document.querySelectorAll("[data-editor-mode]")) {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      actions.setEditorMode(button.dataset.editorMode, {
        modalEditorKey: actions.modalEditorKeyForElement(button),
      });
    });
  }
  $("sidebarToggle").addEventListener("click", actions.toggleSidebar);
  $("sidebarClose").addEventListener("click", actions.closeSidebar);
  $("sidebarBackdrop").addEventListener("click", actions.closeSidebar);
  $("newProblemButton").addEventListener("click", () => actions.openModal("newProblemModal"));
  $("workspaceBuildAllButton").addEventListener("click", () => {
    void actions.withErrors(actions.openWorkspaceBuildModal, "전체 문제 팩 빌드를 준비하는 중입니다.");
  });
  optional("repositoryCloneButton")?.addEventListener("click", actions.openRepositoryModal);
  optional("repositoryRefreshButton")?.addEventListener("click", () => {
    void actions.withErrors(actions.refreshRepositories, "저장소 목록을 새로고침하는 중입니다.");
  });
  optional("repositorySelect")?.addEventListener("change", (event) => {
    void actions.withErrors(
      () => actions.selectRepository(event.target.value),
      "저장소를 전환하는 중입니다."
    );
  });
  optional("repositoryCloneStartButton")?.addEventListener("click", () => {
    void actions.withErrors(actions.cloneRepositoryFromModal, "저장소를 받아오는 중입니다.");
  });
  optional("repositoryRegisterButton")?.addEventListener("click", () => {
    void actions.withErrors(actions.registerRepositoryFromModal, "저장소를 여는 중입니다.");
  });
  optional("gitFetchButton")?.addEventListener("click", () => {
    void actions.withErrors(() => actions.runGitAction("fetch"), "Git fetch를 실행하는 중입니다.");
  });
  optional("gitPullButton")?.addEventListener("click", () => {
    void actions.withErrors(() => actions.runGitAction("pull"), "Git pull을 실행하는 중입니다.");
  });
  optional("gitCommitButton")?.addEventListener("click", () => {
    void actions.withErrors(actions.commitGitChanges, "Git commit을 생성하는 중입니다.");
  });
  optional("gitPushButton")?.addEventListener("click", () => {
    void actions.withErrors(() => actions.runGitAction("push"), "Git push를 실행하는 중입니다.");
  });
  $("bulkSelectAllButton").addEventListener("click", () => {
    for (const input of document.querySelectorAll("[data-bulk-problem]")) input.checked = true;
    actions.updateBulkStartButton();
  });
  $("bulkMaxWorkersInput").addEventListener("input", actions.updateBulkStartButton);
  $("workspaceBuildStartButton").addEventListener("click", () => {
    const problemIds = actions.selectedBulkProblemIdsFromModal();
    actions.closeModals();
    void actions.withInlineErrors(() => actions.buildAllPacksOnce(problemIds));
  });
  $("createProblemButton").addEventListener("click", () => {
    void actions.withErrors(actions.createProblem, "문제를 생성하는 중입니다.");
  });
  $("deleteProblemConfirmInput").addEventListener("input", actions.updateDeleteProblemButton);
  $("deleteProblemButton").addEventListener("click", () => {
    void actions.withErrors(actions.deleteSelectedProblem, "문제를 삭제하는 중입니다.");
  });
  $("saveFileButton").addEventListener("click", () => {
    void actions.withErrors(actions.saveFile, "파일을 저장하는 중입니다.");
  });
  optional("runAllButton")?.addEventListener("click", () => {
    void actions.withErrors(actions.runAllChecksOnce, "전체 테스트를 실행하는 중입니다.");
  });
  optional("packButton")?.addEventListener("click", () => {
    void actions.withInlineErrors(actions.buildPack);
  });
  optional("packStartButton")?.addEventListener("click", () => {
    void actions.withInlineErrors(actions.buildPack);
  });
  optional("lastRunClose")?.addEventListener("click", () => {
    actions.hideLastRunPanel();
  });
  optional("globalTaskStatus")?.addEventListener("click", (event) => {
    if (event.target instanceof HTMLElement && event.target.matches("[data-dismiss-stale-pack-job]")) {
      event.preventDefault();
      void actions.withInlineErrors(actions.dismissStalePackJob);
    }
    if (event.target instanceof HTMLElement && event.target.matches("[data-cancel-pack-job]")) {
      event.preventDefault();
      void actions.withInlineErrors(actions.cancelActivePackJob);
    }
    if (event.target instanceof HTMLElement && event.target.matches("[data-cancel-bulk-job]")) {
      event.preventDefault();
      void actions.withInlineErrors(actions.cancelActiveBulkJob);
    }
  });
  $("solutionCreateButton").addEventListener("click", () => {
    void actions.withErrors(actions.createSolution, "솔루션 파일을 생성하는 중입니다.");
  });
  $("solutionRenameButton").addEventListener("click", () => {
    void actions.withErrors(actions.renameSolution, "솔루션 파일명을 변경하는 중입니다.");
  });
  $("solutionStressStartButton").addEventListener("click", () => {
    void actions.withInlineErrors(actions.runSolutionStress);
  });
  $("solutionStressScope").addEventListener("change", actions.updateSolutionStressScope);
  for (const id of ["solutionCreateName", "solutionCreateExpected", "solutionCreateLanguage"]) {
    $(id).addEventListener("input", actions.updateSolutionPreview);
    $(id).addEventListener("change", actions.updateSolutionPreview);
  }
  for (const id of ["solutionName", "solutionExpected", "solutionLanguage"]) {
    $(id).addEventListener("input", actions.updateSolutionRenamePreview);
    $(id).addEventListener("change", actions.updateSolutionRenamePreview);
  }
  for (const id of [
    "metadataProblemIdInput",
    "metadataTitle",
    "metadataFolder",
    "metadataVersion",
    "metadataDefaultProfile",
    "metadataCompileTimeout",
    "metadataGenerationTimeout",
    "metadataSolutionTimeout",
    "metadataUserTimeout",
    "metadataUserMemoryLimit",
    "metadataToolGenerator",
    "metadataToolGeneratorConfig",
    "metadataToolValidator",
    "metadataToolChecker",
    "metadataToolSolution",
  ]) {
    $(id).addEventListener("input", actions.updateMetadataPreview);
    $(id).addEventListener("change", actions.updateMetadataPreview);
  }
  for (const id of ["packIdInput", "packVerifyProfileInput"]) {
    $(id).addEventListener("input", actions.updateBuildDashboard);
    $(id).addEventListener("change", actions.updateBuildDashboard);
  }
  $("resourceFilterInput").addEventListener("input", (event) => {
    state.resourceFilters[state.selectedTab] = event.target.value;
    actions.renderTabFiles();
  });
  $("solutionUploadInput").addEventListener("change", (event) => {
    void actions.withErrors(async () => {
      await actions.uploadSolutions(Array.from(event.target.files || []));
      event.target.value = "";
    }, "솔루션 파일을 업로드하는 중입니다.");
  });
  for (const button of document.querySelectorAll(".tab-button")) {
    button.addEventListener("click", () => {
      void actions.withErrors(() => actions.selectTab(button.dataset.tab), "탭을 불러오는 중입니다.");
    });
  }
  for (const button of document.querySelectorAll("[data-modal-close]")) {
    button.addEventListener("click", actions.closeModals);
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (activeCodeEditorElement(event) && state.editorMode === "vim") return;
      actions.setEditorSettingsOpen(false);
      actions.closeModals();
      actions.closeSidebar();
    }
  });
  document.addEventListener("click", () => {
    if (state.editorSettingsOpen) actions.setEditorSettingsOpen(false);
  });
  window.addEventListener("beforeunload", (event) => {
    if (!actions.hasUnsavedChanges()) return;
    event.preventDefault();
    event.returnValue = "";
  });
  window.addEventListener("storage", (event) => {
    if (event.key === RUN_ALL_LOCK_KEY) actions.updateGlobalActionState();
    if (event.key === PACK_JOB_KEY) actions.syncPackJobFromStorage();
    if (event.key === LAST_RESULTS_STORAGE_KEY && state.selectedProblem) {
      actions.restoreProblemLastResult(state.selectedProblem);
      actions.renderTaskPanel();
    }
  });
  runAllChannel?.addEventListener("message", (event) => {
    if (event.data?.type === "run-all-lock-changed") actions.updateGlobalActionState();
  });
}
