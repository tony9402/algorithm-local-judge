/**
 * 모달 codemirror 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { optional } from "../dom.js";
import { EDITOR_INDENT, state } from "../state.js";
import {
  codeMirrorModeForLanguage,
  normalizeCodeMirrorVimMode,
} from "./highlight.js";

const modalCallbacks = {
  createSolution: async () => {},
  renameSolution: async () => {},
  updateEditorSettingsUi: () => {},
  withErrors: async (action) => action(),
};
export function configureModalCodeMirror(callbacks = {}) {
  Object.assign(modalCallbacks, callbacks);
}

function withModalErrors(action, message) {
  return modalCallbacks.withErrors(action, message);
}
function modalEditorKeyMap() {
  return state.editorMode === "vim" ? "vim" : "default";
}
/**
 * 모달 before 입력 명령이나 이벤트를 받아 필요한 검증과 서비스 호출을 수행합니다.
 *
 * @param {object} event 브라우저 이벤트 또는 서버 이벤트 스트림에서 받은 이벤트 객체입니다.
 */
function handleModalBeforeInput(event) {
  const wrapperMode = event.target?.closest?.(".CodeMirror")?.dataset?.vimMode;
  const activeMode = wrapperMode || state.vimMode;
  if (state.editorMode === "vim" && activeMode !== "insert") {
    event.preventDefault();
  }
}
function stopVimEscapeFromClosingModal(event) {
  if (event.key === "Escape" && state.editorMode === "vim") {
    event.stopPropagation();
  }
}
export function modalEditorKeyForElement(element) {
  const modal = element?.closest?.("#solutionCreateModal, #solutionEditModal");
  if (modal?.id === "solutionCreateModal") return "create";
  if (modal?.id === "solutionEditModal") return "edit";
  return "";
}
export function focusModalEditor(key) {
  const editor = state.modalEditors[key];
  if (!editor) return;
  window.requestAnimationFrame(() => {
    editor.refresh();
    editor.focus();
  });
}

function modalEditorLanguage(key) {
  return optional(key === "create" ? "solutionCreateLanguage" : "solutionLanguage")?.value || "cpp";
}
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
export function initializeSourceModalEditors() {
  if (!window.CodeMirror) return;
  const configs = [
    {
      key: "create",
      textareaId: "solutionCreateSource",
      languageId: "solutionCreateLanguage",
      save: () => void withModalErrors(modalCallbacks.createSolution, "솔루션 파일을 생성하는 중입니다."),
    },
    {
      key: "edit",
      textareaId: "solutionEditSource",
      languageId: "solutionLanguage",
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
 * 모달 편집기 options 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
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
 * 모달 wrapper mode 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 *
 * @param {any} editor 모달 wrapper mode을 계산하거나 검증할 때 필요한 편집기 입력입니다.
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
export function getModalEditorValue(key) {
  if (state.modalEditors[key]) return state.modalEditors[key].getValue();
  return optional(key === "create" ? "solutionCreateSource" : "solutionEditSource")?.value || "";
}
/**
 * 모달 편집기 value 값을 내부 상태나 DOM 요소에 반영합니다.
 *
 * @param {any} key 상태 맵, 로컬 스토리지, 객체에서 값을 찾는 키입니다.
 * @param {any} value 검증하거나 상태에 반영할 입력 값입니다.
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
 * 모달 편집기 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 *
 * @param {any} key 상태 맵, 로컬 스토리지, 객체에서 값을 찾는 키입니다.
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
