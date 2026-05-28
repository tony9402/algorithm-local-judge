/**
 * 저장소 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { api } from "../api.js";
import { $, optional } from "../dom.js";
import { showResult } from "../feedback.js";
import { state } from "../state.js";

const repositoryCallbacks = {
  closeModals: () => {},
  confirmDiscardChanges: () => true,
  refresh: async () => {},
  syncPackJobFromStorage: () => {},
};
export function configureRepositoryActions(callbacks = {}) {
  Object.assign(repositoryCallbacks, callbacks);
}
function resetProblemStateForRepositoryChange() {
  state.selectedProblem = null;
  state.selectedFile = null;
  state.detail = null;
  state.files = [];
  state.lastSolutionVerification = null;
  state.lastSolutionStress = null;
  state.lastFullTest = null;
  state.lastPackResult = null;
  state.lastRun = null;
  state.dirtySolutionPaths = [];
  state.activeBulkJob = null;
  state.stalePackJob = null;
  if (state.packPollTimer) {
    window.clearTimeout(state.packPollTimer);
    state.packPollTimer = null;
  }
  state.activePackJob = null;
}
/**
 * 저장소 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 */
export function openRepositoryModal() {
  $("repositoryUrlInput").value = "";
  $("repositoryBranchInput").value = "";
  $("repositoryNameInput").value = "";
  repositoryCallbacks.closeModals();
  document.getElementById("repositoryModal")?.classList.remove("hidden");
  window.setTimeout(() => optional("repositoryUrlInput")?.focus(), 0);
}
export async function selectRepository(repoName) {
  const next = repoName || "";
  if (!next || next === (state.activeRepository || "")) return;
  if (!repositoryCallbacks.confirmDiscardChanges()) {
    const select = optional("repositorySelect");
    if (select) select.value = state.activeRepository || "";
    return;
  }
  await api("/api/repositories/select", {
    method: "POST",
    body: JSON.stringify({ repo_name: next }),
  });
  resetProblemStateForRepositoryChange();
  await repositoryCallbacks.refresh();
  repositoryCallbacks.syncPackJobFromStorage();
  showResult(`저장소 ${next}을 열었습니다.`, "summary success");
}
export async function cloneRepositoryFromModal() {
  const url = $("repositoryUrlInput").value.trim();
  const branch = $("repositoryBranchInput").value.trim();
  const repoName = $("repositoryNameInput").value.trim();
  if (!url) throw new Error("Git 저장소를 입력하세요.");
  if (!repositoryCallbacks.confirmDiscardChanges()) return;
  const result = await api("/api/repositories/clone", {
    method: "POST",
    body: JSON.stringify({
      url,
      branch: branch || null,
      repo_name: repoName || null,
    }),
  });
  resetProblemStateForRepositoryChange();
  repositoryCallbacks.closeModals();
  await repositoryCallbacks.refresh();
  repositoryCallbacks.syncPackJobFromStorage();
  const name = result.repository?.name || result.workspace?.activeRepository || repoName || url;
  showResult(`저장소 ${name}을 연결했습니다.`, "summary success");
}
export async function registerRepositoryFromModal() {
  const repoName = $("repositoryNameInput").value.trim();
  if (!repoName) throw new Error("Local 이름을 입력하세요.");
  if (!repositoryCallbacks.confirmDiscardChanges()) return;
  const result = await api("/api/repositories/register", {
    method: "POST",
    body: JSON.stringify({ repo_name: repoName }),
  });
  resetProblemStateForRepositoryChange();
  repositoryCallbacks.closeModals();
  await repositoryCallbacks.refresh();
  repositoryCallbacks.syncPackJobFromStorage();
  const name = result.repository?.name || repoName;
  showResult(`저장소 ${name}을 열었습니다.`, "summary success");
}
/**
 * 저장소 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 */
export async function refreshRepositories() {
  await repositoryCallbacks.refresh();
}
