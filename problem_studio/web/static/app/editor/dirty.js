/**
 * dirty 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { $, setText } from "../dom.js";
import { state } from "../state.js";
import { getEditorValue } from "./codemirror.js";
import { updateEditorStatus } from "./visuals.js";
import { dirtySources } from "../unsaved-changes.js";
export function hasUnsavedChanges() {
  return dirtySources("file").length > 0;
}
/**
 * dirty state 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
export function updateDirtyState() {
  if (!state.selectedFile) return;
  const dirty = hasUnsavedChanges();
  setText("fileStatus", dirty ? "수정됨 · 저장하지 않음" : "저장됨");
  $("saveFileButton").classList.toggle("dirty", dirty);
  updateEditorStatus();
}
export function confirmDiscardChanges() {
  if (!hasUnsavedChanges()) return true;
  return false;
}
