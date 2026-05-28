/**
 * vim mode 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

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
 * vim mode 값을 내부 상태나 DOM 요소에 반영합니다.
 *
 * @param {string} mode vim mode을 계산하거나 검증할 때 필요한 mode 입력입니다.
 * @param {any} editor vim mode을 계산하거나 검증할 때 필요한 편집기 입력입니다.
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
export function editorModeBadgeText() {
  if (state.editorMode !== "vim") return "기본";
  if (state.vimMode === "visual") return "VISUAL";
  if (state.vimMode === "visual-line") return "V-LINE";
  return state.vimMode === "insert" ? "INSERT" : "NORMAL";
}
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
