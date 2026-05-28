import { optional } from "../dom.js";
import { state } from "../state.js";
import { pushEditorHistory } from "./history.js";
import { lineStartAt } from "./position.js";
import {
  clearVimVisualState,
  enterVimVisualMode,
  isVimVisualMode,
  moveEditorCursor,
} from "./selection.js";
import { vimCallbacks } from "./vim-context.js";

/**
 * setVimMode 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} mode `mode` 값입니다.
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function setVimMode(mode, editor = optional("fileEditor"), options = {}) {
  if (state.editorMode !== "vim") return;
  state.vimMode = mode === "insert" || isVimVisualMode(mode) ? mode : "normal";
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  state.vimPreferredColumn = null;
  if (!isVimVisualMode()) clearVimVisualState();
  if (editor) {
    if (state.vimMode === "insert" && options.recordHistory !== false) {
      pushEditorHistory(editor);
    }
    if (state.vimMode === "normal") {
      const lineStart = lineStartAt(editor.value, editor.selectionStart);
      const position = options.fromInsert && editor.selectionStart > lineStart
        ? editor.selectionStart - 1
        : editor.selectionStart;
      moveEditorCursor(editor, position);
    } else if (isVimVisualMode()) {
      enterVimVisualMode(editor, state.vimMode);
    }
  }
  vimCallbacks.updateEditorSettingsUi();
}

/**
 * editorModeBadgeText 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function editorModeBadgeText() {
  if (state.editorMode !== "vim") return "기본";
  if (state.vimMode === "visual") return "VISUAL";
  if (state.vimMode === "visual-line") return "V-LINE";
  return state.vimMode === "insert" ? "INSERT" : "NORMAL";
}

/**
 * resetVimTransientState 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function resetVimTransientState() {
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  state.vimPreferredColumn = null;
  state.vimMessage = "";
  clearVimVisualState();
  vimCallbacks.closeEditorCommandLine();
  if (state.editorMode === "vim") state.vimMode = "normal";
  vimCallbacks.updateEditorSettingsUi();
}
