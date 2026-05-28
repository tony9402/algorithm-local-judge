import { optional } from "./dom.js";
import { state } from "./state.js";

/**
 * openModal 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @param {any} trigger `trigger` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function openModal(id, trigger = document.activeElement) {
  state.activeModalTrigger = trigger instanceof HTMLElement ? trigger : null;
  const modal = optional(id);
  modal?.classList.remove("hidden");
  const firstField = modal?.querySelector("input, select, textarea");
  if (firstField instanceof HTMLElement) firstField.focus();
}

/**
 * activeCodeEditorElement 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} event 발생한 이벤트입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function activeCodeEditorElement(event) {
  const target = event?.target instanceof Element ? event.target : null;
  const active = document.activeElement instanceof Element ? document.activeElement : null;
  return (
    target?.closest(".CodeMirror, .source-modal-editor, #fileEditor")
    || active?.closest(".CodeMirror, .source-modal-editor, #fileEditor")
  );
}

/**
 * closeModals 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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
