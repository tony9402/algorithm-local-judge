import { optional } from "../dom.js";
import { EDITOR_INDENT, state } from "../state.js";
import {
  codeMirrorModeForLanguage,
  normalizeCodeMirrorVimMode,
} from "./highlight.js";

const modalCallbacks = {
  /**
   * createSolution 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  createSolution: async () => {},
  /**
   * renameSolution 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renameSolution: async () => {},
  /**
   * updateEditorSettingsUi 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateEditorSettingsUi: () => {},
  /**
   * withErrors 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} action `action` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  withErrors: async (action) => action(),
};

/**
 * configureModalCodeMirror 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureModalCodeMirror(callbacks = {}) {
  Object.assign(modalCallbacks, callbacks);
}

/**
 * withModalErrors 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} action `action` 값입니다.
 * @param {any} message 메시지입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function withModalErrors(action, message) {
  return modalCallbacks.withErrors(action, message);
}

/**
 * modalEditorKeyMap 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function modalEditorKeyMap() {
  return state.editorMode === "vim" ? "vim" : "default";
}

/**
 * handleModalBeforeInput 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} event 발생한 이벤트입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function handleModalBeforeInput(event) {
  const wrapperMode = event.target?.closest?.(".CodeMirror")?.dataset?.vimMode;
  const activeMode = wrapperMode || state.vimMode;
  if (state.editorMode === "vim" && activeMode !== "insert") {
    event.preventDefault();
  }
}

/**
 * stopVimEscapeFromClosingModal 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} event 발생한 이벤트입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function stopVimEscapeFromClosingModal(event) {
  if (event.key === "Escape" && state.editorMode === "vim") {
    event.stopPropagation();
  }
}

/**
 * modalEditorKeyForElement 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} element `element` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function modalEditorKeyForElement(element) {
  const modal = element?.closest?.("#solutionCreateModal, #solutionEditModal");
  if (modal?.id === "solutionCreateModal") return "create";
  if (modal?.id === "solutionEditModal") return "edit";
  return "";
}

/**
 * focusModalEditor 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} key `key` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function focusModalEditor(key) {
  const editor = state.modalEditors[key];
  if (!editor) return;
  window.requestAnimationFrame(() => {
    editor.refresh();
    editor.focus();
  });
}

/**
 * modalEditorLanguage 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} key `key` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function modalEditorLanguage(key) {
  return optional(key === "create" ? "solutionCreateLanguage" : "solutionLanguage")?.value || "cpp";
}

/**
 * syncModalEditorMode 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} key `key` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function syncModalEditorMode(key) {
  const editor = state.modalEditors[key];
  if (!editor) return;
  const language = modalEditorLanguage(key);
  const nextMode = codeMirrorModeForLanguage(language);
  if (editor.getOption("mode") !== nextMode) {
    editor.setOption("mode", nextMode);
  }
  editor.getWrapperElement().dataset.language = language;
}

/**
 * initializeSourceModalEditors 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function initializeSourceModalEditors() {
  if (!window.CodeMirror) return;
  const configs = [
    {
      key: "create",
      textareaId: "solutionCreateSource",
      languageId: "solutionCreateLanguage",
      /**
       * save 함수를 실행하고 반환 값을 계산합니다.
       *
       * @returns {any} 처리 결과를 반환합니다.
       */
      save: () => void withModalErrors(modalCallbacks.createSolution, "솔루션 파일을 생성하는 중입니다."),
    },
    {
      key: "edit",
      textareaId: "solutionEditSource",
      languageId: "solutionLanguage",
      /**
       * save 함수를 실행하고 반환 값을 계산합니다.
       *
       * @returns {any} 처리 결과를 반환합니다.
       */
      save: () => void withModalErrors(modalCallbacks.renameSolution, "솔루션 파일명을 변경하는 중입니다."),
    },
  ];
  for (const config of configs) {
    if (state.modalEditors[config.key]) continue;
    const textarea = optional(config.textareaId);
    if (!textarea) continue;
    const cm = window.CodeMirror.fromTextArea(textarea, {
      lineNumbers: true,
      mode: codeMirrorModeForLanguage(optional(config.languageId)?.value || "cpp"),
      indentUnit: 4,
      tabSize: 4,
      indentWithTabs: false,
      lineWrapping: false,
      keyMap: modalEditorKeyMap(),
      extraKeys: {
        /**
         * Tab 함수를 실행하고 반환 값을 계산합니다.
         *
         * @param {any} instance `instance` 값입니다.
         * @returns {any} 처리 결과를 반환합니다.
         */
        Tab: (instance) => {
          if (instance.somethingSelected()) instance.indentSelection("add");
          else instance.replaceSelection(EDITOR_INDENT, "end");
        },
        "Shift-Tab": (instance) => instance.indentSelection("subtract"),
        "Ctrl-S": config.save,
        "Cmd-S": config.save,
      },
    });
    cm.on("cursorActivity", () => {
      if (state.editorMode === "vim") cm.scrollIntoView(cm.getCursor(), 48);
    });
    window.CodeMirror.on(cm, "vim-mode-change", (event) => {
      const wrapper = cm.getWrapperElement();
      const nextMode = normalizeCodeMirrorVimMode(event?.mode);
      wrapper.dataset.editorMode = state.editorMode;
      wrapper.dataset.vimMode = nextMode;
      state.vimMode = nextMode;
      modalCallbacks.updateEditorSettingsUi();
    });
    const wrapper = cm.getWrapperElement();
    wrapper.classList.add("source-modal-codemirror", "studio-codemirror");
    wrapper.addEventListener("beforeinput", handleModalBeforeInput, true);
    wrapper.addEventListener("keydown", stopVimEscapeFromClosingModal);
    state.modalEditors[config.key] = cm;
  }
  updateModalEditorOptions();
}

/**
 * updateModalEditorOptions 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function updateModalEditorOptions() {
  const createEditor = state.modalEditors.create;
  const editEditor = state.modalEditors.edit;
  if (createEditor) {
    createEditor.setOption("keyMap", modalEditorKeyMap());
    syncModalEditorMode("create");
    updateModalWrapperMode(createEditor);
  }
  if (editEditor) {
    editEditor.setOption("keyMap", modalEditorKeyMap());
    syncModalEditorMode("edit");
    updateModalWrapperMode(editEditor);
  }
  window.requestAnimationFrame(() => {
    createEditor?.refresh();
    editEditor?.refresh();
  });
}

/**
 * updateModalWrapperMode 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function updateModalWrapperMode(editor) {
  const wrapper = editor.getWrapperElement();
  const previousMode = wrapper.dataset.editorMode;
  wrapper.dataset.editorMode = state.editorMode;
  wrapper.dataset.vimMode =
    state.editorMode === "vim"
      ? previousMode === "vim"
        ? wrapper.dataset.vimMode || "normal"
        : "normal"
      : "insert";
}

/**
 * getModalEditorValue 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} key `key` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function getModalEditorValue(key) {
  if (state.modalEditors[key]) return state.modalEditors[key].getValue();
  return optional(key === "create" ? "solutionCreateSource" : "solutionEditSource")?.value || "";
}

/**
 * setModalEditorValue 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} key `key` 값입니다.
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function setModalEditorValue(key, value) {
  const textareaId = key === "create" ? "solutionCreateSource" : "solutionEditSource";
  const textarea = optional(textareaId);
  if (textarea) textarea.value = value || "";
  const editor = state.modalEditors[key];
  if (editor) {
    editor.setValue(value || "");
    editor.clearHistory();
    syncModalEditorMode(key);
  }
  window.requestAnimationFrame(() => state.modalEditors[key]?.refresh());
}

/**
 * refreshModalEditor 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} key `key` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function refreshModalEditor(key) {
  const editor = state.modalEditors[key];
  if (!editor) return;
  syncModalEditorMode(key);
  window.requestAnimationFrame(() => {
    editor.refresh();
    window.requestAnimationFrame(() => editor.refresh());
  });
}
