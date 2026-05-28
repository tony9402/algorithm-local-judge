/**
 * selection 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import {
  clampNormalCursor,
  editorLineColumn,
  lineEndAt,
  lineStartAt,
  lineWithBreakBounds,
  normalLineCursorEnd,
} from "./position.js";
import { state } from "../state.js";

const selectionCallbacks = {
  ensureEditorCursorVisible: () => {},
  updateEditorSettingsUi: () => {},
  updateEditorStatus: () => {},
};
export function configureEditorSelection(callbacks = {}) {
  Object.assign(selectionCallbacks, callbacks);
}
export function isVimVisualMode(mode = state.vimMode) {
  return mode === "visual" || mode === "visual-line" || mode === "visual-block";
}
export function vimModeClassName() {
  return isVimVisualMode() ? "visual" : state.vimMode;
}
/**
 * vim visual state 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 */
export function clearVimVisualState() {
  state.vimVisualAnchor = null;
  state.vimVisualCursor = null;
}
export function visualSelectionRange(editor) {
  const anchor = state.vimVisualAnchor ?? editor.selectionStart;
  const cursor = state.vimVisualCursor ?? editor.selectionStart;
  if (state.vimMode === "visual-line") {
    const startLine = Math.min(anchor, cursor);
    const endLine = Math.max(anchor, cursor);
    const start = lineStartAt(editor.value, startLine);
    const end = lineWithBreakBounds(editor.value, endLine).end;
    return { start, end };
  }
  const start = Math.min(anchor, cursor);
  const end = Math.min(editor.value.length, Math.max(anchor, cursor) + 1);
  return { start, end };
}
/**
 * visual selection 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 *
 * @param {any} editor visual selection을 계산하거나 검증할 때 필요한 편집기 입력입니다.
 */
export function updateVisualSelection(editor) {
  const { start, end } = visualSelectionRange(editor);
  editor.selectionStart = start;
  editor.selectionEnd = Math.max(start, end);
  selectionCallbacks.ensureEditorCursorVisible(editor);
  selectionCallbacks.updateEditorStatus();
}
export function enterVimVisualMode(editor, mode = "visual") {
  state.vimMode = mode === "visual-line" ? "visual-line" : "visual";
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  const anchor = clampNormalCursor(editor.value, editor.selectionStart);
  state.vimVisualAnchor = anchor;
  state.vimVisualCursor = anchor;
  updateVisualSelection(editor);
  selectionCallbacks.updateEditorSettingsUi();
}
export function exitVimVisualMode(editor) {
  const cursor = state.vimVisualCursor ?? editor.selectionStart;
  state.vimMode = "normal";
  clearVimVisualState();
  moveEditorCursor(editor, cursor);
  selectionCallbacks.updateEditorSettingsUi();
}
export function moveEditorCursor(editor, position, preferredColumn = null, options = {}) {
  const shouldClamp =
    options.normal !== false
    && state.editorMode === "vim"
    && (state.vimMode === "normal" || isVimVisualMode());
  const bounded = shouldClamp
    ? clampNormalCursor(editor.value, position)
    : Math.max(0, Math.min(position, editor.value.length));
  if (state.editorMode === "vim" && isVimVisualMode()) {
    state.vimVisualCursor = bounded;
    state.vimPreferredColumn = preferredColumn;
    updateVisualSelection(editor);
    return;
  }
  editor.selectionStart = bounded;
  editor.selectionEnd = bounded;
  state.vimPreferredColumn = preferredColumn;
  selectionCallbacks.ensureEditorCursorVisible(editor);
  selectionCallbacks.updateEditorStatus();
}
export function activeEditorCursor(editor) {
  return isVimVisualMode() ? state.vimVisualCursor ?? editor.selectionStart : editor.selectionStart;
}
export function moveEditorVertical(editor, direction) {
  const value = editor.value;
  const cursor = activeEditorCursor(editor);
  const { lineStart, column } = editorLineColumn(value, cursor);
  const preferredColumn = state.vimPreferredColumn ?? column;
  let targetLineStart;
  if (direction > 0) {
    const nextBreak = value.indexOf("\n", lineStart);
    if (nextBreak < 0) return;
    targetLineStart = nextBreak + 1;
  } else {
    if (lineStart === 0) return;
    targetLineStart = lineStartAt(value, lineStart - 1);
  }
  if (targetLineStart === lineStart) return;
  const targetLineEnd = state.editorMode === "vim" && state.vimMode === "normal"
    ? normalLineCursorEnd(value, targetLineStart)
    : lineEndAt(value, targetLineStart);
  moveEditorCursor(editor, Math.min(targetLineStart + preferredColumn, targetLineEnd), preferredColumn);
}
export function moveEditorHorizontal(editor, amount) {
  const value = editor.value;
  const selectionStart = activeEditorCursor(editor);
  const lineStart = lineStartAt(value, selectionStart);
  const lineEnd = state.editorMode === "vim" && state.vimMode === "normal"
    ? normalLineCursorEnd(value, lineStart)
    : lineEndAt(value, selectionStart);
  moveEditorCursor(editor, Math.max(lineStart, Math.min(selectionStart + amount, lineEnd)));
}
