/**
 * 모달 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { optional } from "./dom.js";
import { state } from "./state.js";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function visibleFocusable(element) {
  if (!(element instanceof HTMLElement)) return false;
  if (element.getAttribute("aria-hidden") === "true") return false;
  return Boolean(element.offsetParent || element.getClientRects().length);
}
function activeModal() {
  const modals = Array.from(document.querySelectorAll(".modal:not(.hidden)"));
  return modals.at(-1) || null;
}
function focusableElements(modal) {
  return Array.from(modal?.querySelectorAll(FOCUSABLE_SELECTOR) || []).filter(visibleFocusable);
}
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
  modal?.removeAttribute("aria-hidden");
  modal?.setAttribute("tabindex", "-1");
  const firstField = focusableElements(modal)[0] || modal;
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
  for (const id of [
    "newProblemModal",
    "deleteProblemModal",
    "packBuildModal",
    "solutionCreateModal",
    "solutionEditModal",
    "workspaceBuildModal",
    "repositoryModal",
    "solutionCasesModal",
    "solutionStressModal",
    "solutionStressReviewModal",
  ]) {
    const modal = optional(id);
    modal?.classList.add("hidden");
    modal?.setAttribute("aria-hidden", "true");
  }
  state.editingSolutionPath = null;
  if (state.activeModalTrigger && !state.activeModalTrigger.disabled) {
    state.activeModalTrigger.focus();
  }
  state.activeModalTrigger = null;
}

document.addEventListener("keydown", (event) => {
  if (event.key !== "Tab" || event.defaultPrevented) return;
  const modal = activeModal();
  if (!modal) return;
  const focusable = focusableElements(modal);
  if (!focusable.length) {
    event.preventDefault();
    modal.focus();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const current = document.activeElement;
  if (event.shiftKey && (!modal.contains(current) || current === first)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && current === last) {
    event.preventDefault();
    first.focus();
  }
});
