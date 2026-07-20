/**
 * 저장소 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { api } from "../api.js";
import { $, optional } from "../dom.js";
import { showResult } from "../feedback.js";
import { state } from "../state.js";
import { guardUnsavedTransition } from "../unsaved-changes.js";

const repositoryCallbacks = {
  closeModals: () => {},
  openModal: () => {},
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
  state.solutionTestResultsByPath = {};
  state.activeSolutionVerification = null;
  state.activeSolutionTestsByPath = {};
  state.lastFullTest = null;
  state.lastPackResult = null;
  state.lastBulkBuildResult = null;
  state.lastRun = null;
  state.dirtySolutionPaths = [];
  state.activeBulkJob = null;
  state.stalePackJob = null;
  state.activePackJobsByProblem = {};
  state.stalePackJobsByProblem = {};
  if (state.packPollTimer) {
    window.clearTimeout(state.packPollTimer);
    state.packPollTimer = null;
  }
  for (const timer of Object.values(state.packPollTimersByProblem || {})) {
    window.clearTimeout(timer);
  }
  state.packPollTimersByProblem = {};
  state.activePackJob = null;
}
/**
 * 저장소 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 */
export function openRepositoryModal(mode = "clone") {
  if (mode === "open") {
    openRepositoryOpenModal();
    return;
  }
  $("repositoryUrlInput").value = "";
  $("repositoryBranchInput").value = "";
  $("repositoryNameInput").value = "";
  updateRepositoryClonePreview();
  repositoryCallbacks.openModal("repositoryModal", document.activeElement, "repositoryUrlInput");
}

function inferredRepositoryName() {
  const explicit = optional("repositoryNameInput")?.value.trim();
  if (explicit) return explicit;
  const url = optional("repositoryUrlInput")?.value.trim().replace(/[\\/]+$/, "") || "";
  return url.split(/[\\/]/).pop()?.replace(/\.git$/i, "") || "저장소 이름";
}

export function updateRepositoryClonePreview() {
  const preview = optional("repositoryCloneDestination");
  if (preview) preview.textContent = `생성 위치: 문제 workspace / ${inferredRepositoryName()}`;
}

export function renderRepositoryOpenOptions() {
  const select = optional("repositoryOpenSelect");
  const summary = optional("repositoryOpenSummary");
  const start = optional("repositoryOpenStartButton");
  const clone = optional("repositoryOpenCloneButton");
  if (!select || !summary || !start || !clone) return;
  const repositories = state.repositories || [];
  const previous = select.value;
  select.replaceChildren();
  for (const repository of repositories) {
    const option = document.createElement("option");
    option.value = repository.name;
    option.textContent = repository.name;
    select.appendChild(option);
  }
  if (repositories.some((repository) => repository.name === previous)) select.value = previous;
  else if (repositories.some((repository) => repository.name === state.activeRepository)) {
    select.value = state.activeRepository;
  }
  const selected = repositories.find((repository) => repository.name === select.value);
  select.disabled = !selected;
  start.disabled = !selected;
  clone.classList.toggle("hidden", Boolean(selected));
  summary.replaceChildren();
  const title = document.createElement("strong");
  const detail = document.createElement("span");
  title.textContent = selected?.name || "발견된 저장소가 없습니다.";
  detail.textContent = selected
    ? `${selected.branch || "브랜치 정보 없음"} · ${selected.problemCount ?? 0}개 문제`
    : "목록을 새로고침하거나 새 Git 저장소를 복제하세요.";
  summary.append(title, detail);
}

export function openRepositoryOpenModal() {
  renderRepositoryOpenOptions();
  repositoryCallbacks.openModal(
    "repositoryOpenModal",
    document.activeElement,
    state.repositories?.length ? "repositoryOpenSelect" : "repositoryOpenCloneButton"
  );
}

export async function refreshRepositoryOpenList() {
  await refreshRepositories();
  renderRepositoryOpenOptions();
}

export async function openSelectedRepositoryFromModal() {
  const repoName = optional("repositoryOpenSelect")?.value || "";
  if (!repoName) throw new Error("열 저장소를 선택하세요.");
  const completed = await selectRepository(repoName);
  if (completed) repositoryCallbacks.closeModals();
}

export function moveFromRepositoryOpenToClone() {
  repositoryCallbacks.closeModals();
  openRepositoryModal("clone");
}
export async function selectRepository(repoName) {
  const next = repoName || "";
  if (!next) return false;
  if (next === (state.activeRepository || "")) return true;
  const select = optional("repositorySelect");
  const completed = await guardUnsavedTransition(
    "저장소 전환",
    () => selectRepositoryWithoutGuard(next)
  );
  if (!completed && select) select.value = state.activeRepository || "";
  return completed;
}

async function selectRepositoryWithoutGuard(next) {
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
  return guardUnsavedTransition(
    "저장소 복제",
    () => cloneRepositoryFromModalWithoutGuard({ url, branch, repoName })
  );
}

async function cloneRepositoryFromModalWithoutGuard({ url, branch, repoName }) {
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
/**
 * 저장소 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 */
export async function refreshRepositories() {
  return guardUnsavedTransition(
    "저장소 목록 새로고침",
    repositoryCallbacks.refresh,
    { scope: "workspace" }
  );
}
