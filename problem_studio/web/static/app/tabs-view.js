import { $, optional, setText } from "./dom.js";
import { TAB_CONFIGS, state } from "./state.js";
import { VALIDATION_QUEUE_ACTIONS } from "./actions/validation-queue.js";

const tabCallbacks = {
  /**
   * openSolutionUpload 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  openSolutionUpload: () => {},
  /**
   * populateMetadataForm 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  populateMetadataForm: () => {},
  /**
   * renderLastRunPanel 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renderLastRunPanel: () => {},
  /**
   * renderSolutionMetaForm 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renderSolutionMetaForm: () => {},
  /**
   * renderSolutionValidationSummary 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renderSolutionValidationSummary: () => {},
  /**
   * renderTabFiles 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renderTabFiles: () => {},
  /**
   * runTabAction 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  runTabAction: async () => {},
  /**
   * showAlert 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  showAlert: () => {},
  /**
   * updateBuildPanel 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateBuildPanel: () => {},
  /**
   * updateGlobalActionState 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateGlobalActionState: () => {},
  /**
   * withErrors 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} action `action` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  withErrors: async (action) => action(),
  /**
   * withInlineErrors 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} action `action` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  withInlineErrors: async (action) => action(),
};

/**
 * configureTabsView 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureTabsView(callbacks = {}) {
  Object.assign(tabCallbacks, callbacks);
}

/**
 * renderTabButtons 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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
 * renderTabActions 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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
 * updateEditorPanelMode 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function updateEditorPanelMode() {
  const infoMode = state.selectedTab === "info";
  const buildMode = state.selectedTab === "build";
  const solutionsMode = state.selectedTab === "solutions";
  const layout = document.querySelector(".studio-layout");
  layout?.classList.toggle("info-mode", infoMode);
  layout?.classList.toggle("solutions-mode", solutionsMode);
  const editorPanel = document.querySelector(".editor-panel");
  editorPanel?.classList.toggle("build-mode", buildMode);
  editorPanel?.classList.toggle("solutions-hidden", solutionsMode);
  optional("buildDashboard")?.classList.toggle("hidden", !buildMode);
}

/**
 * currentPrimaryAction 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function currentPrimaryAction() {
  return TAB_CONFIGS[state.selectedTab]?.actions?.find((action) => action.primary) || null;
}

/**
 * renderTaskPanel 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function renderTaskPanel() {
  const config = TAB_CONFIGS[state.selectedTab];
  renderTabButtons();
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
  tabCallbacks.renderSolutionValidationSummary();
  tabCallbacks.renderTabFiles();
}
