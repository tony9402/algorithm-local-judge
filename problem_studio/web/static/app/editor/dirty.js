import { $, setText } from "../dom.js";
import { state } from "../state.js";
import { getEditorValue } from "./codemirror.js";
import { updateEditorStatus } from "./visuals.js";

/**
 * hasUnsavedChanges 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function hasUnsavedChanges() {
  return Boolean(state.selectedFile) && getEditorValue() !== state.lastSavedContent;
}

/**
 * updateDirtyState 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function updateDirtyState() {
  if (!state.selectedFile) return;
  const dirty = hasUnsavedChanges();
  setText("fileStatus", dirty ? "수정됨 · 저장하지 않음" : "저장됨");
  $("saveFileButton").classList.toggle("dirty", dirty);
  updateEditorStatus();
}

/**
 * confirmDiscardChanges 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function confirmDiscardChanges() {
  if (!hasUnsavedChanges()) return true;
  return window.confirm("저장하지 않은 변경이 있습니다. 이동하면 변경 내용이 사라집니다. 계속할까요?");
}
