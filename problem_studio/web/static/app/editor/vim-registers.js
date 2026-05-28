/**
 * vim registers 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { state } from "../state.js";
import {
  lineEndAt,
  lineRangeWithBreakBounds,
  lineStartAt,
} from "./position.js";
import {
  clearVimVisualState,
  moveEditorCursor,
  visualSelectionRange,
} from "./selection.js";
import { replaceEditorRange } from "./vim-context.js";
import { setVimMode } from "./vim-mode.js";
/**
 * vim 줄 파일이나 상태 항목을 안전성 검사를 거쳐 제거합니다.
 *
 * @param {any} editor vim 줄을 계산하거나 검증할 때 필요한 편집기 입력입니다.
 * @param {any} count vim 줄을 계산하거나 검증할 때 필요한 count 입력입니다.
 * @param {any} enterInsert vim 줄을 계산하거나 검증할 때 필요한 enter insert 입력입니다.
 */
export function deleteVimLine(editor, count = 1, enterInsert = false) {
  const { value, selectionStart } = editor;
  const { start, end } = lineRangeWithBreakBounds(value, selectionStart, count);
  state.vimRegister = value.slice(start, end);
  state.vimRegisterType = "line";
  replaceEditorRange(editor, start, end, "", start);
  state.vimMessage = `${count} line${count > 1 ? "s" : ""} deleted`;
  if (enterInsert) setVimMode("insert", editor, { recordHistory: false });
}
/**
 * vim 줄 파일을 정책이 허용하는 대상 경로로 복사합니다.
 *
 * @param {any} editor vim 줄을 계산하거나 검증할 때 필요한 편집기 입력입니다.
 * @param {any} count vim 줄을 계산하거나 검증할 때 필요한 count 입력입니다.
 */
export function copyVimLine(editor, count = 1) {
  const { value, selectionStart } = editor;
  const { start, end } = lineRangeWithBreakBounds(value, selectionStart, count);
  state.vimRegister = value.slice(start, end);
  state.vimRegisterType = "line";
  state.vimMessage = `${count} line${count > 1 ? "s" : ""} yanked`;
}
export function pasteVimRegister(editor, before = false, count = 1) {
  if (!state.vimRegister) return;
  const { value, selectionStart } = editor;
  if (state.vimRegisterType === "line") {
    const insertAt = before ? lineStartAt(value, selectionStart) : lineEndAt(value, selectionStart);
    const text = state.vimRegister.endsWith("\n")
      ? state.vimRegister.slice(0, -1)
      : state.vimRegister;
    const repeated = Array.from({ length: count }, () => text).join("\n");
    const insertion = before ? `${repeated}\n` : `\n${repeated}`;
    replaceEditorRange(editor, insertAt, insertAt, insertion, insertAt + (before ? 0 : 1));
    state.vimMessage = "pasted";
    return;
  }
  const insertAt = before ? selectionStart : Math.min(selectionStart + 1, value.length);
  const repeated = state.vimRegister.repeat(count);
  replaceEditorRange(editor, insertAt, insertAt, repeated, insertAt + repeated.length - 1);
  state.vimMessage = "pasted";
}
/**
 * vim range 파일이나 상태 항목을 안전성 검사를 거쳐 제거합니다.
 *
 * @param {any} editor vim range을 계산하거나 검증할 때 필요한 편집기 입력입니다.
 * @param {any} start vim range을 계산하거나 검증할 때 필요한 start 입력입니다.
 * @param {any} end vim range을 계산하거나 검증할 때 필요한 end 입력입니다.
 * @param {any} enterInsert vim range을 계산하거나 검증할 때 필요한 enter insert 입력입니다.
 */
export function deleteVimRange(editor, start, end, enterInsert = false) {
  const rangeStart = Math.max(0, Math.min(start, end));
  const rangeEnd = Math.max(rangeStart, Math.max(start, end));
  if (rangeStart === rangeEnd) return;
  state.vimRegister = editor.value.slice(rangeStart, rangeEnd);
  state.vimRegisterType = "char";
  replaceEditorRange(editor, rangeStart, rangeEnd, "", rangeStart);
  state.vimMessage = enterInsert ? "changed" : "deleted";
  if (enterInsert) setVimMode("insert", editor, { recordHistory: false });
}
/**
 * vim range 파일을 정책이 허용하는 대상 경로로 복사합니다.
 *
 * @param {any} editor vim range을 계산하거나 검증할 때 필요한 편집기 입력입니다.
 * @param {any} start vim range을 계산하거나 검증할 때 필요한 start 입력입니다.
 * @param {any} end vim range을 계산하거나 검증할 때 필요한 end 입력입니다.
 */
export function copyVimRange(editor, start, end) {
  const rangeStart = Math.max(0, Math.min(start, end));
  const rangeEnd = Math.max(rangeStart, Math.max(start, end));
  state.vimRegister = editor.value.slice(rangeStart, rangeEnd);
  state.vimRegisterType = "char";
  state.vimMessage = "yanked";
}
/**
 * vim visual selection 파일을 정책이 허용하는 대상 경로로 복사합니다.
 *
 * @param {any} editor vim visual selection을 계산하거나 검증할 때 필요한 편집기 입력입니다.
 */
export function copyVimVisualSelection(editor) {
  const { start, end } = visualSelectionRange(editor);
  state.vimRegister = editor.value.slice(start, end);
  state.vimRegisterType = state.vimMode === "visual-line" ? "line" : "char";
  state.vimMessage = "visual yanked";
  state.vimMode = "normal";
  clearVimVisualState();
  moveEditorCursor(editor, start);
}
/**
 * vim visual selection 파일이나 상태 항목을 안전성 검사를 거쳐 제거합니다.
 *
 * @param {any} editor vim visual selection을 계산하거나 검증할 때 필요한 편집기 입력입니다.
 * @param {any} enterInsert vim visual selection을 계산하거나 검증할 때 필요한 enter insert 입력입니다.
 */
export function deleteVimVisualSelection(editor, enterInsert = false) {
  const { start, end } = visualSelectionRange(editor);
  state.vimRegister = editor.value.slice(start, end);
  state.vimRegisterType = state.vimMode === "visual-line" ? "line" : "char";
  state.vimMode = "normal";
  clearVimVisualState();
  replaceEditorRange(editor, start, end, "", start);
  state.vimMessage = enterInsert ? "visual changed" : "visual deleted";
  if (enterInsert) setVimMode("insert", editor, { recordHistory: false });
}
export function changeToLineEnd(editor) {
  const end = lineEndAt(editor.value, editor.selectionStart);
  deleteVimRange(editor, editor.selectionStart, end, true);
}
/**
 * 줄 end 파일이나 상태 항목을 안전성 검사를 거쳐 제거합니다.
 *
 * @param {any} editor 줄 end을 계산하거나 검증할 때 필요한 편집기 입력입니다.
 */
export function deleteToLineEnd(editor) {
  const end = lineEndAt(editor.value, editor.selectionStart);
  deleteVimRange(editor, editor.selectionStart, end);
}
