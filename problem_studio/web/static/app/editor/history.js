import { EDITOR_HISTORY_LIMIT, state } from "../state.js";

const historyCallbacks = {
  /**
   * moveEditorCursor 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  moveEditorCursor: () => {},
  /**
   * updateDirtyState 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateDirtyState: () => {},
  /**
   * updateEditorSettingsUi 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateEditorSettingsUi: () => {},
  /**
   * updateEditorVisuals 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateEditorVisuals: () => {},
};

/**
 * configureEditorHistory 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureEditorHistory(callbacks = {}) {
  Object.assign(historyCallbacks, callbacks);
}

/**
 * editorSnapshot 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function editorSnapshot(editor) {
  return {
    value: editor.value,
    selectionStart: editor.selectionStart,
    selectionEnd: editor.selectionEnd,
  };
}

/**
 * restoreEditorSnapshot 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @param {any} snapshot `snapshot` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function restoreEditorSnapshot(editor, snapshot) {
  editor.value = snapshot.value;
  editor.selectionStart = Math.min(snapshot.selectionStart, editor.value.length);
  editor.selectionEnd = Math.min(snapshot.selectionEnd, editor.value.length);
  historyCallbacks.updateEditorVisuals();
  historyCallbacks.updateDirtyState();
}

/**
 * resetEditorHistory 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function resetEditorHistory() {
  state.editorUndoStack = [];
  state.editorRedoStack = [];
}

/**
 * pushEditorHistory 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * undoEditorChange 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * redoEditorChange 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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
