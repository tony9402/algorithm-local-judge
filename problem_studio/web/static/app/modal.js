/**
 * 모달 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { optional } from "./dom.js";
import { state } from "./state.js";
/**
 * 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 *
 * @param {any} id 모달을 계산하거나 검증할 때 필요한 ID 입력입니다.
 * @param {any} trigger 모달을 계산하거나 검증할 때 필요한 trigger 입력입니다.
 */
export function openModal(id, trigger = document.activeElement) {
  state.activeModalTrigger = trigger instanceof HTMLElement ? trigger : null;
  const modal = optional(id);
  modal?.classList.remove("hidden");
  const firstField = modal?.querySelector("input, select, textarea");
  if (firstField instanceof HTMLElement) firstField.focus();
}
export function activeCodeEditorElement(event) {
  const target = event?.target instanceof Element ? event.target : null;
  const active = document.activeElement instanceof Element ? document.activeElement : null;
  return (
    target?.closest(".CodeMirror, .source-modal-editor, #fileEditor")
    || active?.closest(".CodeMirror, .source-modal-editor, #fileEditor")
  );
}
/**
 * modals 모달이나 열린 상태를 닫고 관련 임시 상태를 정리합니다.
 */
export function closeModals() {
  optional("newProblemModal")?.classList.add("hidden");
  optional("deleteProblemModal")?.classList.add("hidden");
  optional("packBuildModal")?.classList.add("hidden");
  optional("solutionCreateModal")?.classList.add("hidden");
  optional("solutionEditModal")?.classList.add("hidden");
  optional("workspaceBuildModal")?.classList.add("hidden");
  optional("repositoryModal")?.classList.add("hidden");
  optional("solutionCasesModal")?.classList.add("hidden");
  optional("solutionStressModal")?.classList.add("hidden");
  optional("solutionStressReviewModal")?.classList.add("hidden");
  state.editingSolutionPath = null;
  state.activeModalTrigger?.focus();
  state.activeModalTrigger = null;
}
