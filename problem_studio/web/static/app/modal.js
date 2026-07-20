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
export function activeModalId() {
  return activeModal()?.id || "";
}
function focusableElements(modal) {
  return Array.from(modal?.querySelectorAll(FOCUSABLE_SELECTOR) || []).filter(visibleFocusable);
}
export function trapFocusWithin(event, surface) {
  if (event.key !== "Tab" || event.defaultPrevented || !surface) return false;
  const focusable = focusableElements(surface);
  if (!focusable.length) {
    event.preventDefault();
    surface.focus();
    return true;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const current = document.activeElement;
  if (event.shiftKey && (!surface.contains(current) || current === first)) {
    event.preventDefault();
    last.focus();
    return true;
  }
  if (!event.shiftKey && (!surface.contains(current) || current === last)) {
    event.preventDefault();
    first.focus();
    return true;
  }
  return false;
}
/**
 * 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 *
 * @param {any} id 모달을 계산하거나 검증할 때 필요한 ID 입력입니다.
 * @param {any} trigger 모달을 계산하거나 검증할 때 필요한 trigger 입력입니다.
 */
export function openModal(
  id,
  trigger = document.activeElement,
  initialFocus = null,
) {
  const modal = optional(id);
  if (!modal) return false;
  state.activeModalTrigger = trigger instanceof HTMLElement ? trigger : null;
  state.activeModalTriggerId = state.activeModalTrigger?.id || "";
  state.activeModalTriggerAction = state.activeModalTrigger?.dataset.actionId || "";
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  modal.setAttribute("tabindex", "-1");
  const requested = typeof initialFocus === "string"
    ? optional(initialFocus)
    : initialFocus;
  const firstField = (
    requested instanceof HTMLElement
    && modal.contains(requested)
    && visibleFocusable(requested)
      ? requested
      : modal.querySelector("[data-modal-initial-focus]")
  ) || focusableElements(modal)[0] || modal;
  if (firstField instanceof HTMLElement) firstField.focus();
  return true;
}

function modalTriggerFallback() {
  if (state.activeModalTriggerId) {
    const trigger = document.getElementById(state.activeModalTriggerId);
    if (trigger instanceof HTMLElement && visibleFocusable(trigger)) return trigger;
  }
  if (state.activeModalTriggerAction) {
    const trigger = document.querySelector(
      `#tabActions [data-action-id="${CSS.escape(state.activeModalTriggerAction)}"]`
    );
    if (trigger instanceof HTMLElement && visibleFocusable(trigger)) return trigger;
  }
  return Array.from(document.querySelectorAll(
    "#sidebarToggle, #newProblemButton, #workspaceBuildAllButton, #repositoryCloneButton, #repositoryOpenButton"
  )).find((trigger) => visibleFocusable(trigger) && !trigger.disabled) || null;
}

function restoreModalFocus() {
  const trigger = state.activeModalTrigger?.isConnected
    && !state.activeModalTrigger.disabled
    ? state.activeModalTrigger
    : modalTriggerFallback();
  if (trigger instanceof HTMLElement && !trigger.disabled) {
    trigger.focus();
    return true;
  }
  return false;
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
  const openModals = Array.from(document.querySelectorAll(".modal:not(.hidden)"));
  for (const modal of document.querySelectorAll(".modal")) {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    modal.removeAttribute("data-vim-escape-armed");
  }
  state.editingSolutionPath = null;
  if (openModals.length) restoreModalFocus();
  state.activeModalTrigger = null;
  state.activeModalTriggerId = "";
  state.activeModalTriggerAction = "";
  return openModals.length > 0;
}

export function closeModalSurface(surfaceId) {
  const modal = optional(surfaceId);
  if (!modal || modal.classList.contains("hidden")) return false;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  modal.removeAttribute("data-vim-escape-armed");
  if (["solutionCreateModal", "solutionEditModal"].includes(surfaceId)) {
    state.editingSolutionPath = null;
  }
  restoreModalFocus();
  state.activeModalTrigger = null;
  state.activeModalTriggerId = "";
  state.activeModalTriggerAction = "";
  return true;
}

document.addEventListener("keydown", (event) => {
  const modal = activeModal();
  if (!modal) return;
  trapFocusWithin(event, modal);
});
