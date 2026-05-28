/**
 * vim operations 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { state } from "../state.js";
import {
  currentLineBounds,
  currentLineIndent,
  currentLineNumber,
  firstTextColumn,
  lineEndAt,
  lineRangeWithBreakBounds,
  lineStartAt,
  lineStartByNumber,
  lineWithBreakBounds,
  nextWordEndIndex,
  nextWordPosition,
  normalCursorEndAt,
  previousWordPosition,
  totalLineCount,
} from "./position.js";
import {
  activeEditorCursor,
  clearVimVisualState,
  exitVimVisualMode,
  moveEditorCursor,
  moveEditorHorizontal,
  moveEditorVertical,
  updateVisualSelection,
} from "./selection.js";
import { replaceEditorRange, vimCallbacks } from "./vim-context.js";
import {
  changeToLineEnd,
  copyVimLine,
  copyVimRange,
  copyVimVisualSelection,
  deleteToLineEnd,
  deleteVimLine,
  deleteVimRange,
  deleteVimVisualSelection,
  pasteVimRegister,
} from "./vim-registers.js";
import { setVimMode } from "./vim-mode.js";

export { changeToLineEnd, deleteToLineEnd, pasteVimRegister } from "./vim-registers.js";
export function moveToNextWord(editor, count = 1) {
  let position = activeEditorCursor(editor);
  for (let index = 0; index < count; index += 1) {
    const next = nextWordPosition(editor.value, position);
    if (next === position) break;
    position = next;
  }
  moveEditorCursor(editor, position);
}
export function moveToWordEnd(editor, count = 1) {
  let position = activeEditorCursor(editor);
  for (let index = 0; index < count; index += 1) {
    const next = nextWordEndIndex(editor.value, position);
    if (next === position) break;
    position = next;
  }
  moveEditorCursor(editor, position);
}
export function moveToPreviousWord(editor, count = 1) {
  let position = activeEditorCursor(editor);
  for (let index = 0; index < count; index += 1) {
    const previous = previousWordPosition(editor.value, position);
    if (previous === position) break;
    position = previous;
  }
  moveEditorCursor(editor, position);
}
export function moveToLine(editor, lineNumber) {
  const targetLine = Math.max(1, Math.min(lineNumber, totalLineCount(editor.value)));
  const start = lineStartByNumber(editor.value, targetLine);
  moveEditorCursor(editor, firstTextColumn(editor.value, start, lineEndAt(editor.value, start)));
}
export function insertVimLine(editor, above) {
  const { value, selectionStart } = editor;
  const { start, end } = currentLineBounds(value, selectionStart);
  const indent = currentLineIndent(value, selectionStart);
  if (above) {
    const text = `${indent}\n`;
    replaceEditorRange(editor, start, start, text, start + indent.length);
  } else {
    const text = `\n${indent}`;
    replaceEditorRange(editor, end, end, text, end + text.length);
  }
  setVimMode("insert", editor, { recordHistory: false });
}
/**
 * vim char 파일이나 상태 항목을 안전성 검사를 거쳐 제거합니다.
 *
 * @param {any} editor vim char을 계산하거나 검증할 때 필요한 편집기 입력입니다.
 */
export function deleteVimChar(editor) {
  const { value, selectionStart } = editor;
  if (selectionStart >= value.length || value[selectionStart] === "\n") return;
  state.vimRegister = value.slice(selectionStart, selectionStart + 1);
  state.vimRegisterType = "char";
  replaceEditorRange(editor, selectionStart, selectionStart + 1, "", selectionStart);
}
export function replaceVimChar(editor, value) {
  if (!value || value.length !== 1) return;
  const { selectionStart } = editor;
  if (editor.value[selectionStart] === "\n" || selectionStart >= editor.value.length) return;
  replaceEditorRange(editor, selectionStart, selectionStart + 1, value, selectionStart);
  state.vimMessage = `replaced with ${value}`;
}
export function joinVimLines(editor, count = 1) {
  let position = editor.selectionStart;
  for (let index = 0; index < count; index += 1) {
    const end = lineEndAt(editor.value, position);
    if (end >= editor.value.length) break;
    replaceEditorRange(editor, end, end + 1, " ", end + 1);
    position = end;
  }
  state.vimMessage = "joined";
}
export function findVimSearch(editor, direction = state.vimSearchDirection, fromCurrent = false) {
  const query = state.vimSearchQuery;
  if (!query) return;
  const value = editor.value;
  const start = fromCurrent
    ? editor.selectionStart + (direction > 0 ? 1 : -1)
    : editor.selectionStart + direction;
  let found = -1;
  if (direction > 0) {
    found = value.indexOf(query, Math.max(0, start));
    if (found < 0) found = value.indexOf(query, 0);
  } else {
    found = value.lastIndexOf(query, Math.max(0, start));
    if (found < 0) found = value.lastIndexOf(query);
  }
  if (found >= 0) {
    moveEditorCursor(editor, found);
    state.vimMessage = `${query} 찾음`;
  } else {
    state.vimMessage = `${query} 없음`;
  }
  vimCallbacks.updateEditorSettingsUi();
}

function motionTarget(editor, key, count = 1, explicitLine = null) {
  const { value, selectionStart } = editor;
  if (key === "w") {
    let position = selectionStart;
    for (let index = 0; index < count; index += 1) position = nextWordPosition(value, position);
    return { start: selectionStart, end: position };
  }
  if (key === "b") {
    let position = selectionStart;
    for (let index = 0; index < count; index += 1) position = previousWordPosition(value, position);
    return { start: position, end: selectionStart };
  }
  if (key === "$" || key === "End") return { start: selectionStart, end: lineEndAt(value, selectionStart) };
  if (key === "0") return { start: lineStartAt(value, selectionStart), end: selectionStart };
  if (key === "^") {
    const { start, end } = currentLineBounds(value, selectionStart);
    return { start: firstTextColumn(value, start, end), end: selectionStart };
  }
  if (key === "j" || key === "ArrowDown") {
    return lineRangeWithBreakBounds(value, selectionStart, count + 1);
  }
  if (key === "k" || key === "ArrowUp") {
    const current = currentLineNumber(value, selectionStart);
    const targetStart = lineStartByNumber(value, Math.max(1, current - count));
    const currentEnd = lineWithBreakBounds(value, selectionStart).end;
    return { start: targetStart, end: currentEnd };
  }
  if (key === "G") {
    const targetLine = explicitLine || totalLineCount(value);
    const currentLine = currentLineNumber(value, selectionStart);
    const firstLine = Math.min(currentLine, targetLine);
    const lastLine = Math.max(currentLine, targetLine);
    return {
      start: lineStartByNumber(value, firstLine),
      end: lineRangeWithBreakBounds(value, lineStartByNumber(value, lastLine), 1).end,
    };
  }
  return null;
}
export function vimCountValue(defaultValue = 1) {
  const count = state.vimCount ? Number(state.vimCount) : defaultValue;
  state.vimCount = "";
  return Number.isFinite(count) && count > 0 ? count : defaultValue;
}
/**
 * vim pending 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 *
 * @param {string} message 사용자에게 표시하거나 커밋/진행 상태에 기록할 메시지입니다.
 */
export function clearVimPending(message = "") {
  state.vimPending = "";
  state.vimCount = "";
  state.vimOperatorCount = 1;
  if (message) state.vimMessage = message;
  vimCallbacks.updateEditorSettingsUi();
}
export function applyVimOperator(editor, key) {
  const operator = state.vimPending;
  const explicitMotionCount = state.vimCount ? Number(state.vimCount) : null;
  const count = state.vimOperatorCount * vimCountValue(1);
  if ((operator === "d" || operator === "y" || operator === "c") && key === operator) {
    if (operator === "d") deleteVimLine(editor, count);
    if (operator === "y") copyVimLine(editor, count);
    if (operator === "c") deleteVimLine(editor, count, true);
    clearVimPending();
    return true;
  }
  const target = motionTarget(editor, key, count, explicitMotionCount);
  if (!target) {
    clearVimPending();
    return true;
  }
  if (operator === "d") deleteVimRange(editor, target.start, target.end);
  if (operator === "y") copyVimRange(editor, target.start, target.end);
  if (operator === "c") deleteVimRange(editor, target.start, target.end, true);
  clearVimPending();
  return true;
}
export function handleVimVisualKey(editor, key) {
  if (state.vimPending === "g") {
    if (key === "g") {
      moveToLine(editor, state.vimOperatorCount);
      clearVimPending();
      return true;
    }
    clearVimPending();
    return true;
  }
  const count = () => vimCountValue(1);
  const { value } = editor;
  if (key === "v" && state.vimMode === "visual") {
    exitVimVisualMode(editor);
  } else if (key === "V" && state.vimMode === "visual-line") {
    exitVimVisualMode(editor);
  } else if (key === "V") {
    state.vimMode = "visual-line";
    updateVisualSelection(editor);
    vimCallbacks.updateEditorSettingsUi();
  } else if (key === "v") {
    state.vimMode = "visual";
    updateVisualSelection(editor);
    vimCallbacks.updateEditorSettingsUi();
  } else if (key === "o") {
    const anchor = state.vimVisualAnchor;
    state.vimVisualAnchor = state.vimVisualCursor;
    state.vimVisualCursor = anchor;
    updateVisualSelection(editor);
  } else if (key === "y") {
    copyVimVisualSelection(editor);
  } else if (key === "d" || key === "x" || key === "Delete") {
    deleteVimVisualSelection(editor);
  } else if (key === "c" || key === "s") {
    deleteVimVisualSelection(editor, true);
  } else if (key === "h" || key === "ArrowLeft") {
    moveEditorHorizontal(editor, -count());
  } else if (key === "l" || key === "ArrowRight") {
    moveEditorHorizontal(editor, count());
  } else if (key === "j" || key === "ArrowDown") {
    const amount = count();
    for (let index = 0; index < amount; index += 1) moveEditorVertical(editor, 1);
  } else if (key === "k" || key === "ArrowUp") {
    const amount = count();
    for (let index = 0; index < amount; index += 1) moveEditorVertical(editor, -1);
  } else if (key === "0" || key === "Home") {
    moveEditorCursor(editor, lineStartAt(value, state.vimVisualCursor ?? editor.selectionStart));
  } else if (key === "^") {
    const cursor = state.vimVisualCursor ?? editor.selectionStart;
    const { start, end } = currentLineBounds(value, cursor);
    moveEditorCursor(editor, firstTextColumn(value, start, end));
  } else if (key === "$" || key === "End") {
    moveEditorCursor(editor, normalCursorEndAt(value, state.vimVisualCursor ?? editor.selectionStart));
  } else if (key === "w") {
    moveToNextWord(editor, count());
  } else if (key === "e") {
    moveToWordEnd(editor, count());
  } else if (key === "b") {
    moveToPreviousWord(editor, count());
  } else if (key === "g") {
    state.vimPending = "g";
    state.vimOperatorCount = vimCountValue(1);
    vimCallbacks.updateEditorSettingsUi();
  } else if (key === "G") {
    moveToLine(editor, state.vimCount ? vimCountValue(1) : totalLineCount(value));
  } else {
    clearVimPending();
  }
  return true;
}
