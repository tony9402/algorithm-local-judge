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
  /**
   * ensureEditorCursorVisible 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  ensureEditorCursorVisible: () => {},
  /**
   * updateEditorSettingsUi 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateEditorSettingsUi: () => {},
  /**
   * updateEditorStatus 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateEditorStatus: () => {},
};

/**
 * configureEditorSelection 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureEditorSelection(callbacks = {}) {
  Object.assign(selectionCallbacks, callbacks);
}

/**
 * isVimVisualMode 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} mode `mode` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function isVimVisualMode(mode = state.vimMode) {
  return mode === "visual" || mode === "visual-line" || mode === "visual-block";
}

/**
 * vimModeClassName 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function vimModeClassName() {
  return isVimVisualMode() ? "visual" : state.vimMode;
}

/**
 * clearVimVisualState 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function clearVimVisualState() {
  state.vimVisualAnchor = null;
  state.vimVisualCursor = null;
}

/**
 * visualSelectionRange 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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
 * updateVisualSelection 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function updateVisualSelection(editor) {
  const { start, end } = visualSelectionRange(editor);
  editor.selectionStart = start;
  editor.selectionEnd = Math.max(start, end);
  selectionCallbacks.ensureEditorCursorVisible(editor);
  selectionCallbacks.updateEditorStatus();
}

/**
 * enterVimVisualMode 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @param {any} mode `mode` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * exitVimVisualMode 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function exitVimVisualMode(editor) {
  const cursor = state.vimVisualCursor ?? editor.selectionStart;
  state.vimMode = "normal";
  clearVimVisualState();
  moveEditorCursor(editor, cursor);
  selectionCallbacks.updateEditorSettingsUi();
}

/**
 * moveEditorCursor 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @param {any} position `position` 값입니다.
 * @param {any} preferredColumn `preferredColumn` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * activeEditorCursor 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function activeEditorCursor(editor) {
  return isVimVisualMode() ? state.vimVisualCursor ?? editor.selectionStart : editor.selectionStart;
}

/**
 * moveEditorVertical 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @param {any} direction `direction` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * moveEditorHorizontal 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @param {any} amount `amount` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function moveEditorHorizontal(editor, amount) {
  const value = editor.value;
  const selectionStart = activeEditorCursor(editor);
  const lineStart = lineStartAt(value, selectionStart);
  const lineEnd = state.editorMode === "vim" && state.vimMode === "normal"
    ? normalLineCursorEnd(value, lineStart)
    : lineEndAt(value, selectionStart);
  moveEditorCursor(editor, Math.max(lineStart, Math.min(selectionStart + amount, lineEnd)));
}
