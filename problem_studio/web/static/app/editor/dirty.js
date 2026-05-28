import { $, setText } from "../dom.js";
import { state } from "../state.js";
import { getEditorValue } from "./codemirror.js";
import { updateEditorStatus } from "./visuals.js";

export function hasUnsavedChanges() {
  return Boolean(state.selectedFile) && getEditorValue() !== state.lastSavedContent;
}

export function updateDirtyState() {
  if (!state.selectedFile) return;
  const dirty = hasUnsavedChanges();
  setText("fileStatus", dirty ? "수정됨 · 저장하지 않음" : "저장됨");
  $("saveFileButton").classList.toggle("dirty", dirty);
  updateEditorStatus();
}

export function confirmDiscardChanges() {
  if (!hasUnsavedChanges()) return true;
  return window.confirm("저장하지 않은 변경이 있습니다. 이동하면 변경 내용이 사라집니다. 계속할까요?");
}
