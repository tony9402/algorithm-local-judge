import { $ } from "../dom.js";
import { EDITOR_INDENT, state } from "../state.js";
import {
  codeMirrorModeForPath,
  normalizeCodeMirrorVimMode,
} from "./highlight.js";
import {
  configureModalCodeMirror,
  updateModalEditorOptions as refreshModalEditorOptions,
} from "./modal-codemirror.js";
import { nextWordEndIndex, nextWordPosition, previousWordPosition } from "./position.js";

export {
  focusModalEditor,
  getModalEditorValue,
  initializeSourceModalEditors,
  modalEditorKeyForElement,
  refreshModalEditor,
  setModalEditorValue,
  updateModalEditorOptions,
} from "./modal-codemirror.js";

const codeMirrorCallbacks = {
  createSolution: async () => {},
  handleEditorCompositionEnd: () => {},
  handleEditorCompositionStart: () => {},
  handleEditorInput: () => {},
  renameSolution: async () => {},
  saveFile: async () => {},
  updateEditorSettingsUi: () => {},
  updateEditorStatus: () => {},
  updateEditorVisuals: () => {},
  withErrors: async (action) => action(),
};

export function configureCodeMirror(callbacks = {}) {
  Object.assign(codeMirrorCallbacks, callbacks);
  configureModalCodeMirror(callbacks);
}

function withConfiguredErrors(action, message) {
  return codeMirrorCallbacks.withErrors(action, message);
}

export function getEditorValue() {
  return state.codeMirror ? state.codeMirror.getValue() : $("fileEditor").value;
}

export function setEditorValue(value, options = {}) {
  const nextValue = value || "";
  state.editorApplyingValue = true;
  $("fileEditor").value = nextValue;
  if (state.codeMirror && state.codeMirror.getValue() !== nextValue) {
    state.codeMirror.setValue(nextValue);
    if (options.clearHistory) state.codeMirror.clearHistory();
  }
  state.editorApplyingValue = false;
  codeMirrorCallbacks.updateEditorVisuals();
}

export function focusEditor() {
  if (state.codeMirror) state.codeMirror.focus();
  else $("fileEditor").focus();
}

export function editorCursorOffset() {
  if (!state.codeMirror) return $("fileEditor").selectionStart || 0;
  return state.codeMirror.indexFromPos(state.codeMirror.getCursor());
}

export function updateCodeMirrorOptions() {
  if (!state.codeMirror) return;
  const nextMode = codeMirrorModeForPath(state.selectedFile);
  const nextKeyMap = state.editorMode === "vim" ? "vim" : "default";
  if (state.codeMirror.getOption("mode") !== nextMode) {
    state.codeMirror.setOption("mode", nextMode);
  }
  if (state.codeMirror.getOption("keyMap") !== nextKeyMap) {
    state.codeMirror.setOption("keyMap", nextKeyMap);
  }
  window.requestAnimationFrame(() => state.codeMirror?.refresh());
  refreshModalEditorOptions();
}

export function moveCodeMirrorCursorToIndex(index) {
  if (!state.codeMirror) return;
  const cursor = state.codeMirror.posFromIndex(Math.max(0, Math.min(index, state.codeMirror.getValue().length)));
  state.codeMirror.setCursor(cursor);
  state.codeMirror.scrollIntoView(cursor, 48);
  codeMirrorCallbacks.updateEditorStatus();
}

export function handleCodeMirrorVimFallback(event) {
  if (!state.codeMirror || state.editorMode !== "vim" || state.vimMode !== "normal") return false;
  if (event.metaKey || event.ctrlKey || event.altKey || event.isComposing || event.keyCode === 229) return false;
  const key = event.key;
  const cursor = state.codeMirror.getCursor();
  const value = state.codeMirror.getValue();
  const offset = state.codeMirror.indexFromPos(cursor);
  const prevent = () => {
    event.preventDefault();
    event.stopPropagation();
  };
  if (state.codeMirrorPendingKey === "g") {
    state.codeMirrorPendingKey = "";
    if (key === "g") {
      prevent();
      state.codeMirror.setCursor({ line: 0, ch: 0 });
      state.codeMirror.scrollIntoView({ line: 0, ch: 0 }, 48);
      return true;
    }
  }
  if (key === "g") {
    prevent();
    state.codeMirrorPendingKey = "g";
    return true;
  }
  state.codeMirrorPendingKey = "";
  if (key === "k" || key === "ArrowUp") {
    prevent();
    state.codeMirror.setCursor({
      line: Math.max(0, cursor.line - 1),
      ch: cursor.ch,
    });
    state.codeMirror.scrollIntoView(state.codeMirror.getCursor(), 48);
    return true;
  }
  if (key === "j" || key === "ArrowDown") {
    prevent();
    state.codeMirror.setCursor({
      line: Math.min(state.codeMirror.lineCount() - 1, cursor.line + 1),
      ch: cursor.ch,
    });
    state.codeMirror.scrollIntoView(state.codeMirror.getCursor(), 48);
    return true;
  }
  if (key === "h" || key === "ArrowLeft") {
    prevent();
    moveCodeMirrorCursorToIndex(offset - 1);
    return true;
  }
  if (key === "l" || key === "ArrowRight") {
    prevent();
    moveCodeMirrorCursorToIndex(offset + 1);
    return true;
  }
  if (key === "e") {
    prevent();
    moveCodeMirrorCursorToIndex(nextWordEndIndex(value, offset));
    return true;
  }
  if (key === "w") {
    prevent();
    moveCodeMirrorCursorToIndex(nextWordPosition(value, offset));
    return true;
  }
  if (key === "b") {
    prevent();
    moveCodeMirrorCursorToIndex(previousWordPosition(value, offset));
    return true;
  }
  if (key === "0" || key === "Home") {
    prevent();
    state.codeMirror.setCursor({ line: cursor.line, ch: 0 });
    return true;
  }
  if (key === "^") {
    prevent();
    const line = state.codeMirror.getLine(cursor.line) || "";
    const first = line.search(/\S/);
    state.codeMirror.setCursor({ line: cursor.line, ch: first < 0 ? 0 : first });
    return true;
  }
  if (key === "$" || key === "End") {
    prevent();
    state.codeMirror.setCursor({ line: cursor.line, ch: (state.codeMirror.getLine(cursor.line) || "").length });
    return true;
  }
  if (key === "G") {
    prevent();
    const line = state.codeMirror.lineCount() - 1;
    state.codeMirror.setCursor({ line, ch: 0 });
    state.codeMirror.scrollIntoView({ line, ch: 0 }, 48);
    return true;
  }
  return false;
}

function handleCodeMirrorBeforeChange(_instance, change) {
  if (state.editorApplyingValue) return;
  const blocksTextInput = state.editorMode === "vim" && state.vimMode !== "insert";
  const origin = String(change.origin || "");
  if (blocksTextInput && (origin === "+input" || origin === "paste" || /compose/i.test(origin))) {
    change.cancel();
  }
}

function handleCodeMirrorBeforeInput(event) {
  const wrapperMode = event.target?.closest?.(".CodeMirror")?.dataset?.vimMode;
  const activeMode = wrapperMode || state.vimMode;
  if (state.editorMode === "vim" && activeMode !== "insert") {
    event.preventDefault();
  }
}

function handleCodeMirrorChange(instance) {
  if (state.editorApplyingValue) return;
  $("fileEditor").value = instance.getValue();
  codeMirrorCallbacks.handleEditorInput();
}

export function initializeCodeMirror() {
  if (state.codeMirror || !window.CodeMirror) return;
  const editor = $("fileEditor");
  const cm = window.CodeMirror.fromTextArea(editor, {
    lineNumbers: true,
    mode: codeMirrorModeForPath(state.selectedFile),
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    lineWrapping: false,
    keyMap: state.editorMode === "vim" ? "vim" : "default",
    showCursorWhenSelecting: true,
    extraKeys: {
      Tab: (instance) => {
        if (instance.somethingSelected()) instance.indentSelection("add");
        else instance.replaceSelection(EDITOR_INDENT, "end");
      },
      "Shift-Tab": (instance) => instance.indentSelection("subtract"),
      "Ctrl-S": () => void withConfiguredErrors(codeMirrorCallbacks.saveFile, "파일을 저장하는 중입니다."),
      "Cmd-S": () => void withConfiguredErrors(codeMirrorCallbacks.saveFile, "파일을 저장하는 중입니다."),
    },
  });
  state.codeMirror = cm;
  cm.on("beforeChange", handleCodeMirrorBeforeChange);
  cm.on("change", handleCodeMirrorChange);
  cm.on("cursorActivity", () => {
    codeMirrorCallbacks.updateEditorStatus();
    if (state.editorMode === "vim") cm.scrollIntoView(cm.getCursor(), 48);
  });
  cm.on("scroll", codeMirrorCallbacks.updateEditorStatus);
  window.CodeMirror.on(cm, "vim-mode-change", (event) => {
    state.vimMode = normalizeCodeMirrorVimMode(event?.mode);
    codeMirrorCallbacks.updateEditorSettingsUi();
  });
  if (window.CodeMirror.Vim?.defineEx) {
    window.CodeMirror.Vim.defineEx("write", "w", () => {
      void withConfiguredErrors(codeMirrorCallbacks.saveFile, "파일을 저장하는 중입니다.");
    });
  }
  const wrapper = cm.getWrapperElement();
  wrapper.classList.add("studio-codemirror");
  wrapper.addEventListener("beforeinput", handleCodeMirrorBeforeInput, true);
  wrapper.addEventListener("compositionstart", codeMirrorCallbacks.handleEditorCompositionStart, true);
  wrapper.addEventListener("compositionend", codeMirrorCallbacks.handleEditorCompositionEnd, true);
  updateCodeMirrorOptions();
}
