/**
 * 파일, 메타데이터 폼, 솔루션 모달의 저장되지 않은 변경을 하나의 전환 계약으로 보호합니다.
 */

import { optional } from "./dom.js";
import { state } from "./state.js";

const callbacks = {
  currentFileContent: () => "",
  currentMetadataDraft: () => ({}),
  currentSolutionModalDraft: () => null,
  discardFile: () => {},
  discardMetadata: () => {},
  discardSolutionModal: () => {},
  forceCloseSurface: () => false,
  saveFile: async () => {},
  saveMetadata: async () => {},
  saveSolutionModal: async () => {},
};

let promptResolver = null;
let promptSuppressedLoading = false;
let transitionSequence = 0;

export function configureUnsavedChanges(nextCallbacks = {}) {
  Object.assign(callbacks, nextCallbacks);
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function currentUnsavedContextKey(problemId = state.selectedProblem) {
  if (!problemId) return "";
  return `${state.activeRepository || "legacy"}:${problemId}`;
}

export function rememberFileSnapshot(path = state.selectedFile, content = callbacks.currentFileContent()) {
  const contextKey = currentUnsavedContextKey();
  state.unsaved.file = {
    contextKey: contextKey && path ? `${contextKey}:${path}` : "",
    path: path || "",
    savedContent: String(content ?? ""),
  };
}

export function clearFileSnapshot() {
  state.unsaved.file = { contextKey: "", path: "", savedContent: "" };
}

export function rememberMetadataSnapshot(draft = callbacks.currentMetadataDraft()) {
  state.unsaved.metadata = {
    contextKey: currentUnsavedContextKey(),
    savedCanonicalDraft: canonical(draft || {}),
  };
}

export function clearMetadataSnapshot() {
  state.unsaved.metadata = { contextKey: "", savedCanonicalDraft: "" };
}

export function rememberSolutionModalSnapshot(mode, path = "", draft = callbacks.currentSolutionModalDraft()) {
  state.unsaved.solutionModal = {
    contextKey: currentUnsavedContextKey(),
    mode: mode || "",
    path: path || "",
    savedCanonicalDraft: canonical(draft || {}),
  };
}

export function clearSolutionModalSnapshot() {
  state.unsaved.solutionModal = {
    contextKey: "",
    mode: "",
    path: "",
    savedCanonicalDraft: "",
  };
}

function requestedKinds(scope) {
  if (!scope || scope === "all") return new Set(["file", "metadata", "solutionModal"]);
  if (scope === "workspace") return new Set(["file", "metadata"]);
  if (scope === "solutionModal") return new Set(["solutionModal"]);
  return new Set(Array.isArray(scope) ? scope : [scope]);
}

export function dirtySources(scope = "all") {
  const sources = [];
  const kinds = requestedKinds(scope);
  const contextKey = currentUnsavedContextKey();
  const file = state.unsaved.file;
  if (
    kinds.has("file")
    && file.contextKey === `${contextKey}:${state.selectedFile || ""}`
    && String(callbacks.currentFileContent() ?? "") !== file.savedContent
  ) {
    sources.push({ kind: "file", label: file.path || "열린 파일", contextKey: file.contextKey });
  }
  const metadata = state.unsaved.metadata;
  if (
    kinds.has("metadata")
    && Boolean(metadata.contextKey)
    && metadata.contextKey === contextKey
    && canonical(callbacks.currentMetadataDraft() || {}) !== metadata.savedCanonicalDraft
  ) {
    sources.push({ kind: "metadata", label: "문제 정보", contextKey: metadata.contextKey });
  }
  const solution = state.unsaved.solutionModal;
  const solutionModalId = solution.mode === "create" ? "solutionCreateModal" : "solutionEditModal";
  if (
    kinds.has("solutionModal")
    && Boolean(solution.contextKey)
    && solution.contextKey === contextKey
    && !optional(solutionModalId)?.classList.contains("hidden")
    && canonical(callbacks.currentSolutionModalDraft() || {}) !== solution.savedCanonicalDraft
  ) {
    sources.push({
      kind: "solutionModal",
      label: solution.path || (solution.mode === "create" ? "새 솔루션" : "솔루션 편집"),
      contextKey: solution.contextKey,
    });
  }
  return sources;
}

export function hasAnyUnsavedChanges() {
  return dirtySources().length > 0;
}

function hasMetadataConflict(sources) {
  return sources.some((source) => source.kind === "metadata")
    && sources.some((source) => source.kind === "file" && state.unsaved.file.path === "problem.json");
}

function closePrompt(decision) {
  const modal = optional("unsavedChangesModal");
  modal?.classList.add("hidden");
  modal?.setAttribute("aria-hidden", "true");
  if (promptSuppressedLoading && state.loadingDepth > 0) {
    optional("loadingOverlay")?.classList.remove("hidden");
  }
  promptSuppressedLoading = false;
  const resolve = promptResolver;
  promptResolver = null;
  resolve?.(decision);
}

export function cancelUnsavedPrompt() {
  if (!promptResolver) return false;
  closePrompt("cancel");
  return true;
}

function promptForDecision(intent, sources) {
  const modal = optional("unsavedChangesModal");
  if (!modal) return Promise.resolve("cancel");
  optional("unsavedChangesDescription").textContent = `${intent} 전에 변경사항을 저장하거나 버리세요.`;
  const list = optional("unsavedChangesSources");
  list.replaceChildren();
  for (const source of sources) {
    const item = document.createElement("li");
    item.textContent = source.label;
    list.appendChild(item);
  }
  const conflict = hasMetadataConflict(sources);
  const conflictPanel = optional("unsavedChangesConflict");
  conflictPanel?.classList.toggle("hidden", !conflict);
  if (conflictPanel) {
    conflictPanel.textContent = conflict
      ? "problem.json 원본과 문제 정보 폼이 모두 변경되었습니다. 자동 병합하지 않습니다. 취소한 뒤 한쪽을 먼저 저장하거나 되돌리세요."
      : "";
  }
  const saveButton = optional("unsavedChangesSaveButton");
  if (saveButton) {
    saveButton.disabled = conflict;
    saveButton.title = conflict ? "원본과 폼의 동시 변경은 자동 저장할 수 없습니다." : "";
  }
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  const loadingOverlay = optional("loadingOverlay");
  promptSuppressedLoading = Boolean(loadingOverlay && !loadingOverlay.classList.contains("hidden"));
  if (promptSuppressedLoading) loadingOverlay.classList.add("hidden");
  window.requestAnimationFrame(() => optional("unsavedChangesCancelButton")?.focus());
  return new Promise((resolve) => {
    promptResolver = resolve;
  });
}

export async function saveDirtySources(sources) {
  for (const source of sources) {
    if (source.kind === "file") await callbacks.saveFile({ silent: true });
    if (source.kind === "metadata") await callbacks.saveMetadata({ silent: true });
    if (source.kind === "solutionModal") await callbacks.saveSolutionModal();
  }
}

export function discardDirtySources(sources) {
  for (const source of sources) {
    if (source.kind === "file") callbacks.discardFile(state.unsaved.file.savedContent);
    if (source.kind === "metadata") callbacks.discardMetadata(state.unsaved.metadata.savedCanonicalDraft);
    if (source.kind === "solutionModal") {
      callbacks.discardSolutionModal(state.unsaved.solutionModal.savedCanonicalDraft);
    }
  }
}

export async function guardUnsavedTransition(intent, transition, options = {}) {
  if (state.pendingTransitionId !== null) return false;
  const sources = dirtySources(options.scope || "all");
  if (!sources.length) {
    await transition();
    return true;
  }
  const transitionId = ++transitionSequence;
  state.pendingTransitionId = transitionId;
  try {
    const decision = await promptForDecision(intent, sources);
    if (decision === "cancel") return false;
    if (decision === "save") await saveDirtySources(sources);
    if (decision === "discard") discardDirtySources(sources);
    if (state.pendingTransitionId !== transitionId) return false;
    await transition();
    return true;
  } finally {
    if (state.pendingTransitionId === transitionId) state.pendingTransitionId = null;
  }
}

export function requestCloseSurface(surfaceId) {
  if (surfaceId === "unsavedChangesModal") return Promise.resolve(cancelUnsavedPrompt());
  const scope = ["solutionCreateModal", "solutionEditModal"].includes(surfaceId)
    ? "solutionModal"
    : "all";
  return guardUnsavedTransition(
    "화면 닫기",
    () => callbacks.forceCloseSurface(surfaceId),
    { scope }
  );
}

export function bindUnsavedChangesModal() {
  optional("unsavedChangesCancelButton")?.addEventListener("click", () => closePrompt("cancel"));
  optional("unsavedChangesDiscardButton")?.addEventListener("click", () => closePrompt("discard"));
  optional("unsavedChangesSaveButton")?.addEventListener("click", () => closePrompt("save"));
}
