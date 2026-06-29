/**
 * tabs 화면 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { $, optional, setText } from "./dom.js";
import { renderFeedbackPanels } from "./feedback.js";
import { TAB_CONFIGS, state } from "./state.js";
import { VALIDATION_QUEUE_ACTIONS } from "./actions/validation-queue.js";

const tabCallbacks = {
  openSolutionUpload: () => {},
  populateMetadataForm: () => {},
  renderLastRunPanel: () => {},
  renderSolutionMetaForm: () => {},
  renderSolutionValidationSummary: () => {},
  renderTabFiles: () => {},
  runTabAction: async () => {},
  showAlert: () => {},
  updateBuildPanel: () => {},
  updateGlobalActionState: () => {},
  withErrors: async (action) => action(),
  withInlineErrors: async (action) => action(),
};
export function configureTabsView(callbacks = {}) {
  Object.assign(tabCallbacks, callbacks);
}
/**
 * tab buttons 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderTabButtons() {
  for (const button of document.querySelectorAll(".tab-button")) {
    const active = button.dataset.tab === state.selectedTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    if (active) button.scrollIntoView({ block: "nearest", inline: "center" });
  }
}
/**
 * tab actions 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderTabActions() {
  const actions = $("tabActions");
  actions.innerHTML = "";
  for (const action of TAB_CONFIGS[state.selectedTab].actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    if (action.id === "runAllChecks") button.id = "runAllButton";
    if (action.id === "buildPack") button.id = "packButton";
    if (action.id === "buildAllPacks") button.id = "buildAllPacksButton";
    if (action.primary) button.className = "primary";
    if (action.danger) button.className = "danger";
    button.addEventListener("click", () => {
      if (action.id === "uploadSolutions") {
        try {
          tabCallbacks.openSolutionUpload();
        } catch (error) {
          tabCallbacks.showAlert(error.message, "error", {
            title: "솔루션 업로드 실패",
            timeout: 9000,
          });
        }
        return;
      }
      const runner = VALIDATION_QUEUE_ACTIONS.has(action.id)
        ? tabCallbacks.withInlineErrors
        : tabCallbacks.withErrors;
      void runner(
        () => tabCallbacks.runTabAction(action.id),
        `${action.label} 작업을 실행하는 중입니다.`
      );
    });
    actions.appendChild(button);
  }
  tabCallbacks.updateGlobalActionState();
}
/**
 * 편집기 panel mode 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
export function updateEditorPanelMode() {
  const infoMode = state.selectedTab === "info";
  const buildMode = state.selectedTab === "build";
  const solutionsMode = state.selectedTab === "solutions";
  const layout = document.querySelector(".studio-layout");
  layout?.classList.toggle("info-mode", infoMode);
  layout?.classList.toggle("solutions-mode", solutionsMode);
  document.querySelector(".workspace")?.classList.toggle("solutions-mode", solutionsMode);
  const editorPanel = document.querySelector(".editor-panel");
  editorPanel?.classList.toggle("build-mode", buildMode);
  editorPanel?.classList.toggle("solutions-hidden", solutionsMode);
  optional("buildDashboard")?.classList.toggle("hidden", !buildMode);
}
export function currentPrimaryAction() {
  return TAB_CONFIGS[state.selectedTab]?.actions?.find((action) => action.primary) || null;
}
/**
 * task panel 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
export function renderTaskPanel() {
  const config = TAB_CONFIGS[state.selectedTab];
  renderTabButtons();
  updateEditorPanelMode();
  setText("taskTitle", config.title);
  setText("taskDescription", config.description);
  $("metadataForm").classList.toggle("hidden", state.selectedTab !== "info");
  tabCallbacks.renderSolutionMetaForm();
  tabCallbacks.updateBuildPanel();
  tabCallbacks.renderLastRunPanel();
  if (state.selectedTab === "info" && state.detail) {
    tabCallbacks.populateMetadataForm(state.detail.metadata);
  }
  renderTabActions();
  renderFeedbackPanels();
  tabCallbacks.renderSolutionValidationSummary();
  tabCallbacks.renderTabFiles();
}
