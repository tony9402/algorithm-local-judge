/**
 * 이력 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { EDITOR_HISTORY_LIMIT, state } from "../state.js";

const historyCallbacks = {
  moveEditorCursor: () => {},
  updateDirtyState: () => {},
  updateEditorSettingsUi: () => {},
  updateEditorVisuals: () => {},
};
export function configureEditorHistory(callbacks = {}) {
  Object.assign(historyCallbacks, callbacks);
}
export function editorSnapshot(editor) {
  return {
    value: editor.value,
    selectionStart: editor.selectionStart,
    selectionEnd: editor.selectionEnd,
  };
}
export function restoreEditorSnapshot(editor, snapshot) {
  editor.value = snapshot.value;
  editor.selectionStart = Math.min(snapshot.selectionStart, editor.value.length);
  editor.selectionEnd = Math.min(snapshot.selectionEnd, editor.value.length);
  historyCallbacks.updateEditorVisuals();
  historyCallbacks.updateDirtyState();
}
export function resetEditorHistory() {
  state.editorUndoStack = [];
  state.editorRedoStack = [];
}
export function pushEditorHistory(editor) {
  const snapshot = editorSnapshot(editor);
  const previous = state.editorUndoStack[state.editorUndoStack.length - 1];
  if (previous && previous.value === snapshot.value && previous.selectionStart === snapshot.selectionStart) {
    return;
  }
  state.editorUndoStack.push(snapshot);
  if (state.editorUndoStack.length > EDITOR_HISTORY_LIMIT) state.editorUndoStack.shift();
  state.editorRedoStack = [];
}
export function undoEditorChange(editor) {
  const snapshot = state.editorUndoStack.pop();
  if (!snapshot) {
    state.vimMessage = "되돌릴 변경이 없습니다";
    historyCallbacks.updateEditorSettingsUi();
    return;
  }
  state.editorRedoStack.push(editorSnapshot(editor));
  restoreEditorSnapshot(editor, snapshot);
  state.vimMessage = "undo";
  if (state.editorMode === "vim" && state.vimMode === "normal") {
    historyCallbacks.moveEditorCursor(editor, editor.selectionStart);
  }
  historyCallbacks.updateEditorSettingsUi();
}
export function redoEditorChange(editor) {
  const snapshot = state.editorRedoStack.pop();
  if (!snapshot) {
    state.vimMessage = "다시 실행할 변경이 없습니다";
    historyCallbacks.updateEditorSettingsUi();
    return;
  }
  state.editorUndoStack.push(editorSnapshot(editor));
  restoreEditorSnapshot(editor, snapshot);
  state.vimMessage = "redo";
  if (state.editorMode === "vim" && state.vimMode === "normal") {
    historyCallbacks.moveEditorCursor(editor, editor.selectionStart);
  }
  historyCallbacks.updateEditorSettingsUi();
}
