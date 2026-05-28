import { $, optional, setText } from "../dom.js";
import { EDITOR_INDENT, EDITOR_SETTINGS_KEY, state } from "../state.js";
import { readStorage, writeStorage } from "../storage.js";
import {
  configureCodeMirror,
  focusEditor,
  focusModalEditor,
  getEditorValue,
  setEditorValue,
  updateCodeMirrorOptions,
  updateModalEditorOptions,
} from "./codemirror.js";
import { updateDirtyState } from "./dirty.js";
import { configureEditorHistory, pushEditorHistory } from "./history.js";
import {
  clearVimVisualState,
  configureEditorSelection,
  isVimVisualMode,
  moveEditorCursor,
  vimModeClassName,
} from "./selection.js";
import {
  ensureEditorCursorVisible,
  syncEditorScroll,
  updateEditorStatus,
  updateEditorVisuals,
} from "./visuals.js";
import {
  configureEditorVim,
  editorModeBadgeText,
  findVimSearch,
  handleVimKeydown,
  resetVimTransientState,
} from "./vim.js";

export { syncEditorScroll, updateEditorStatus, updateEditorVisuals } from "./visuals.js";
export { confirmDiscardChanges, hasUnsavedChanges, updateDirtyState } from "./dirty.js";

const coreCallbacks = {
  /**
   * createSolution 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  createSolution: async () => {},
  /**
   * currentPrimaryAction 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  currentPrimaryAction: () => null,
  /**
   * renameSolution 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renameSolution: async () => {},
  /**
   * runTabAction 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  runTabAction: async () => {},
  /**
   * saveFile 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  saveFile: async () => {},
  /**
   * withErrors 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} action `action` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  withErrors: async (action) => action(),
};

/**
 * configureEditorCore 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureEditorCore(callbacks = {}) {
  Object.assign(coreCallbacks, callbacks);
  configureEditorHistory({
    moveEditorCursor,
    updateDirtyState,
    updateEditorSettingsUi,
    updateEditorVisuals,
  });
  configureEditorSelection({
    ensureEditorCursorVisible,
    updateEditorSettingsUi,
    updateEditorStatus,
  });
  configureEditorVim({
    closeEditorCommandLine,
    openEditorCommandLine,
    replaceEditorRange,
    updateEditorSettingsUi,
  });
  configureCodeMirror({
    createSolution: coreCallbacks.createSolution,
    handleEditorCompositionEnd,
    handleEditorCompositionStart,
    handleEditorInput,
    renameSolution: coreCallbacks.renameSolution,
    saveFile: coreCallbacks.saveFile,
    updateEditorSettingsUi,
    updateEditorStatus,
    updateEditorVisuals,
    withErrors: coreCallbacks.withErrors,
  });
}

/**
 * replaceEditorRange 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @param {any} start `start` 값입니다.
 * @param {any} end `end` 값입니다.
 * @param {any} replacement `replacement` 값입니다.
 * @param {any} cursorPosition `cursorPosition` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function replaceEditorRange(editor, start, end, replacement, cursorPosition = start + replacement.length) {
  pushEditorHistory(editor);
  editor.setRangeText(replacement, start, end, "end");
  moveEditorCursor(editor, cursorPosition);
  updateEditorVisuals();
  updateDirtyState();
}

/**
 * setEditorMode 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} mode `mode` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function setEditorMode(mode, options = {}) {
  state.editorMode = mode === "vim" ? "vim" : "default";
  state.vimMode = state.editorMode === "vim" ? "normal" : "insert";
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  state.vimMessage = "";
  state.vimPreferredColumn = null;
  clearVimVisualState();
  writeStorage(EDITOR_SETTINGS_KEY, { mode: state.editorMode });
  if (state.codeMirror) {
    updateCodeMirrorOptions();
  } else if (state.editorMode === "vim") {
    moveEditorCursor($("fileEditor"), $("fileEditor").selectionStart);
  }
  updateModalEditorOptions();
  updateEditorSettingsUi();
  if (options.modalEditorKey) {
    focusModalEditor(options.modalEditorKey);
  } else if (options.focus !== false) {
    focusEditor();
  }
}

/**
 * updateEditorSettingsUi 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function updateEditorSettingsUi() {
  const isVim = state.editorMode === "vim";
  for (const button of document.querySelectorAll("[data-editor-mode]")) {
    const active = button.dataset.editorMode === state.editorMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  }
  optional("editorSettingsButton")?.setAttribute(
    "aria-expanded",
    state.editorSettingsOpen ? "true" : "false"
  );
  optional("editorSettingsPanel")?.classList.toggle("hidden", !state.editorSettingsOpen);
  const badge = optional("editorModeBadge");
  if (badge) {
    badge.textContent = editorModeBadgeText();
    badge.className = `editor-mode-badge ${
      isVim ? (state.vimMode === "insert" ? "vim-insert" : `vim-${vimModeClassName()}`) : ""
    }`.trim();
  }
  const codeEditor = optional("codeEditor");
  if (codeEditor) {
    codeEditor.dataset.editorMode = state.editorMode;
    codeEditor.dataset.vimMode = state.vimMode;
  }
  updateEditorStatus();
}

/**
 * setEditorSettingsOpen 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} open `open` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function setEditorSettingsOpen(open) {
  state.editorSettingsOpen = open;
  updateEditorSettingsUi();
}

/**
 * restoreEditorSettings 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function restoreEditorSettings() {
  const saved = readStorage(EDITOR_SETTINGS_KEY);
  state.editorMode = saved?.mode === "vim" ? "vim" : "default";
  state.vimMode = state.editorMode === "vim" ? "normal" : "insert";
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  state.vimMessage = "";
  clearVimVisualState();
  state.editorSettingsOpen = false;
  updateCodeMirrorOptions();
  updateEditorSettingsUi();
}

/**
 * openEditorCommandLine 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} mode `mode` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function openEditorCommandLine(mode) {
  state.editorCommandMode = mode;
  const panel = optional("editorCommandLine");
  const input = optional("editorCommandInput");
  setText("editorCommandPrefix", mode === "search" ? "/" : ":");
  panel?.classList.remove("hidden");
  if (input) {
    input.value = "";
    input.focus();
  }
}

/**
 * closeEditorCommandLine 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function closeEditorCommandLine() {
  state.editorCommandMode = "";
  optional("editorCommandLine")?.classList.add("hidden");
  const input = optional("editorCommandInput");
  if (input) input.value = "";
}

/**
 * submitEditorCommandLine 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function submitEditorCommandLine() {
  const input = optional("editorCommandInput");
  const editor = optional("fileEditor");
  if (!input || !editor) return;
  const value = input.value.trim();
  const mode = state.editorCommandMode;
  closeEditorCommandLine();
  editor.focus();
  if (!value) return;
  if (mode === "search") {
    state.vimSearchQuery = value;
    state.vimSearchDirection = 1;
    findVimSearch(editor, 1, true);
    return;
  }
  if (value === "w" || value === "write") {
    void coreCallbacks.withErrors(coreCallbacks.saveFile, "파일을 저장하는 중입니다.");
    state.vimMessage = "write";
  } else {
    state.vimMessage = `지원하지 않는 명령: ${value}`;
  }
  updateEditorSettingsUi();
}

/**
 * handleEditorInput 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function handleEditorInput() {
  if (state.editorApplyingValue) return;
  if (
    !state.codeMirror
    && state.editorMode === "vim"
    && state.vimMode !== "insert"
    && $("fileEditor").value !== state.editorSnapshotBeforeIme
  ) {
    $("fileEditor").value = state.editorSnapshotBeforeIme;
  }
  updateEditorVisuals();
  updateDirtyState();
}

/**
 * handleEditorCompositionStart 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} event 발생한 이벤트입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function handleEditorCompositionStart(event) {
  state.editorComposing = true;
  state.editorSnapshotBeforeIme = getEditorValue();
  if (state.editorMode === "vim" && state.vimMode !== "insert") {
    event.preventDefault();
  }
}

/**
 * handleEditorCompositionEnd 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function handleEditorCompositionEnd() {
  if (state.editorMode === "vim" && state.vimMode !== "insert") {
    setEditorValue(state.editorSnapshotBeforeIme);
  }
  state.editorComposing = false;
}

/**
 * indentEditorSelection 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function indentEditorSelection(editor) {
  const { value, selectionStart, selectionEnd } = editor;
  pushEditorHistory(editor);
  if (selectionStart !== selectionEnd && value.slice(selectionStart, selectionEnd).includes("\n")) {
    const lineStart = value.lastIndexOf("\n", selectionStart - 1) + 1;
    const selectedEnd =
      selectionEnd > selectionStart && value[selectionEnd - 1] === "\n"
        ? selectionEnd - 1
        : selectionEnd;
    const selected = value.slice(lineStart, selectedEnd);
    const indented = selected.replace(/^/gm, EDITOR_INDENT);
    editor.value = value.slice(0, lineStart) + indented + value.slice(selectedEnd);
    const diff = indented.length - selected.length;
    editor.selectionStart = selectionStart + EDITOR_INDENT.length;
    editor.selectionEnd = selectionEnd + diff;
    return;
  }
  editor.setRangeText(EDITOR_INDENT, selectionStart, selectionEnd, "end");
}

/**
 * outdentEditorSelection 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function outdentEditorSelection(editor) {
  const { value, selectionStart, selectionEnd } = editor;
  pushEditorHistory(editor);
  const lineStart = value.lastIndexOf("\n", selectionStart - 1) + 1;
  const selectedEnd =
    selectionEnd > selectionStart && value[selectionEnd - 1] === "\n"
      ? selectionEnd - 1
      : selectionEnd;
  const selected = value.slice(lineStart, selectedEnd);
  let removedBeforeStart = 0;
  let removedBeforeEnd = 0;
  let offset = lineStart;
  const outdented = selected
    .split("\n")
    .map((line) => {
      const removeCount = line.startsWith("\t")
        ? 1
        : Math.min(EDITOR_INDENT.length, line.match(/^ */)?.[0].length || 0);
      if (offset < selectionStart) removedBeforeStart += removeCount;
      if (offset < selectionEnd) removedBeforeEnd += removeCount;
      offset += line.length + 1;
      return line.slice(removeCount);
    })
    .join("\n");
  editor.value = value.slice(0, lineStart) + outdented + value.slice(selectedEnd);
  editor.selectionStart = Math.max(lineStart, selectionStart - removedBeforeStart);
  editor.selectionEnd = Math.max(editor.selectionStart, selectionEnd - removedBeforeEnd);
}

/**
 * handleEditorKeydown 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} event 발생한 이벤트입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function handleEditorKeydown(event) {
  const shortcut = event.metaKey || event.ctrlKey;
  if (shortcut && event.key.toLowerCase() === "s") {
    event.preventDefault();
    void coreCallbacks.withErrors(coreCallbacks.saveFile, "파일을 저장하는 중입니다.");
    return;
  }
  if (shortcut && event.key === "Enter") {
    const primary = coreCallbacks.currentPrimaryAction();
    if (primary) {
      event.preventDefault();
      void coreCallbacks.withErrors(
        () => coreCallbacks.runTabAction(primary.id),
        `${primary.label} 작업을 실행하는 중입니다.`
      );
    }
    return;
  }
  if (shortcut && event.key.toLowerCase() === "p") {
    const filter = optional("resourceFilterInput");
    if (filter && !filter.classList.contains("hidden")) {
      event.preventDefault();
      filter.focus();
      filter.select();
      return;
    }
  }
  if (handleVimKeydown(event)) return;
  if (event.key !== "Tab") return;
  event.preventDefault();
  const editor = event.currentTarget;
  if (event.shiftKey) {
    outdentEditorSelection(editor);
  } else {
    indentEditorSelection(editor);
  }
  updateEditorVisuals();
  updateDirtyState();
}

/**
 * handleEditorBeforeInput 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} event 발생한 이벤트입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function handleEditorBeforeInput(event) {
  if (state.editorMode === "vim" && (state.vimMode === "normal" || isVimVisualMode())) {
    event.preventDefault();
  }
}

/**
 * bindEditorEvents 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function bindEditorEvents() {
  $("fileEditor").addEventListener("input", handleEditorInput);
  $("fileEditor").addEventListener("beforeinput", handleEditorBeforeInput);
  $("fileEditor").addEventListener("keydown", handleEditorKeydown);
  $("fileEditor").addEventListener("keyup", updateEditorStatus);
  $("fileEditor").addEventListener("click", updateEditorStatus);
  $("fileEditor").addEventListener("select", updateEditorStatus);
  $("fileEditor").addEventListener("scroll", syncEditorScroll);
  $("fileEditor").addEventListener("compositionstart", handleEditorCompositionStart);
  $("fileEditor").addEventListener("compositionend", handleEditorCompositionEnd);
}

export { getEditorValue, setEditorValue };
export { resetVimTransientState };
