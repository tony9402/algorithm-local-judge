import { optional } from "./dom.js";
import { state } from "./state.js";

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
