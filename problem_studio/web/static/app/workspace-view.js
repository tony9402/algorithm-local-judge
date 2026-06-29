/**
 * 작업 공간 화면 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { $, escapeHtml, optional, setText } from "./dom.js";
import { currentProblemResult } from "./results.js";
import { state } from "./state.js";
import { rememberView } from "./view-persistence.js";

const workspaceCallbacks = {
  selectProblem: async () => {},
  withErrors: async (action) => action(),
};
export function configureWorkspaceView(callbacks = {}) {
  Object.assign(workspaceCallbacks, callbacks);
}
/**
 * mobile header 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 *
 * @param {any} title mobile header을 계산하거나 검증할 때 필요한 title 입력입니다.
 * @param {any} meta mobile header을 계산하거나 검증할 때 필요한 meta 입력입니다.
 */
export function updateMobileHeader(title = null, meta = null) {
  const problemTitle = title || optional("problemTitle")?.textContent || "문제를 선택하세요";
  const problemMeta = meta || (state.selectedProblem ? "문제 목록" : "문제 목록 열기");
  setText("mobileHeaderTitle", problemTitle);
  setText("mobileHeaderMeta", problemMeta);
  const menuAction = document.body.classList.contains("sidebar-open")
    ? "문제 목록 닫기"
    : "문제 목록 열기";
  optional("sidebarToggle")?.setAttribute("aria-label", `${menuAction}: ${problemTitle}`);
}
/**
 * sidebar open 값을 내부 상태나 DOM 요소에 반영합니다.
 *
 * @param {boolean} open sidebar open을 계산하거나 검증할 때 필요한 open 입력입니다.
 */
export function setSidebarOpen(open) {
  document.body.classList.toggle("sidebar-open", open);
  optional("sidebarToggle")?.setAttribute("aria-expanded", open ? "true" : "false");
  updateMobileHeader();
}
/**
 * sidebar 표시 상태를 현재 값의 반대로 전환합니다.
 */
export function toggleSidebar() {
  setSidebarOpen(!document.body.classList.contains("sidebar-open"));
}
/**
 * sidebar 모달이나 열린 상태를 닫고 관련 임시 상태를 정리합니다.
 */
export function closeSidebar() {
  setSidebarOpen(false);
}
export function problemLabel(problem) {
  return `${problem.problemId} ${problem.title || ""}`.trim();
}
export function folderLabel(folder) {
  return String(folder || "").trim() || "기본";
}
function problemValidationStatus(problem) {
  const result = currentProblemResult(problem.problemId, state.activeRepository || null);
  const fullTest = result?.fullTest || null;
  if (fullTest?.passed === false) {
    return {
      className: "problem-status-failed",
      badgeClass: "failed",
      label: "문제 있음",
      title: `${problemLabel(problem)} · ${fullTest.failureStageLabel || fullTest.failureStage || "검증"} 확인 필요`,
    };
  }
  if (result?.dirtyAfterFullTest) {
    return {
      className: "problem-status-stale",
      badgeClass: "stale",
      label: "재검증",
      title: `${problemLabel(problem)} · ${result.dirtyReason || "전체 테스트 재검증 필요"}`,
    };
  }
  if (fullTest?.passed === true) {
    return {
      className: "problem-status-passed",
      badgeClass: "passed",
      label: "통과",
      title: `${problemLabel(problem)} · 전체 테스트 통과`,
    };
  }
  return null;
}

function problemFolderKey(folder) {
  return folderLabel(folder);
}
function isProblemFolderCollapsed(folder) {
  return state.problemFolderCollapsed[problemFolderKey(folder)] === true;
}
/**
 * 문제 폴더 표시 상태를 현재 값의 반대로 전환합니다.
 *
 * @param {any} folder 문제 폴더을 계산하거나 검증할 때 필요한 폴더 입력입니다.
 */
function toggleProblemFolder(folder) {
  const key = problemFolderKey(folder);
  if (state.problemFolderCollapsed[key]) {
    delete state.problemFolderCollapsed[key];
  } else {
    state.problemFolderCollapsed[key] = true;
  }
  rememberView();
  renderProblems(state.problems);
}

function problemFolderSummaries(problems) {
  const counts = {};
  for (const problem of problems || []) {
    const folder = String(problem.folder || "").trim();
    counts[folder] = (counts[folder] || 0) + 1;
  }
  return Object.keys(counts)
    .sort((left, right) => {
      const leftDefault = left === "";
      const rightDefault = right === "";
      if (leftDefault !== rightDefault) return leftDefault ? 1 : -1;
      return left.localeCompare(right);
    })
    .map((folder) => ({
      name: folder,
      label: folderLabel(folder),
      problemCount: counts[folder],
    }));
}
export function syncWorkspaceProblemSummaries() {
  if (!state.workspace) return;
  state.workspace = {
    ...state.workspace,
    problems: state.problems,
    problemIds: state.problems.map((problem) => problem.problemId),
    problemCount: state.problems.length,
    folders: problemFolderSummaries(state.problems),
  };
  renderWorkspace(state.workspace);
}
/**
 * 작업 공간 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {object} data 파일, API 응답, UI 렌더링에 사용할 구조화된 데이터입니다.
 */
export function renderWorkspace(data) {
  state.workspace = data;
  state.repositories = data.repositories || [];
  state.activeRepository = data.activeRepository || null;
  state.repositoryMode = Boolean(data.repositoryMode);
  renderRepositorySelector(data);
  setText(
    "workspaceLabel",
    state.activeRepository ? `문제 저장소 · ${state.activeRepository}` : "문제 제작 워크스페이스"
  );
  if (!state.selectedProblem) {
    updateMobileHeader("문제를 선택하세요", `${data.problemCount}개 문제`);
  }
  const folders = data.folders || [];
  const folderText = folders.length
    ? folders.map((folder) => `${folder.label} ${folder.problemCount}`).join(" · ")
    : "폴더 없음";
  $("workspaceStatus").innerHTML = `
    <div>문제 수: ${data.problemCount}</div>
    <div class="workspace-ok">폴더: ${escapeHtml(folderText)}</div>
    ${
      data.warning
        ? `<div class="danger-note">${escapeHtml(data.warning.message || data.warning.title || "")}</div>`
        : ""
    }
  `;
}
/**
 * 저장소 selector 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {object} data 파일, API 응답, UI 렌더링에 사용할 구조화된 데이터입니다.
 */
export function renderRepositorySelector(data = state.workspace || {}) {
  const select = optional("repositorySelect");
  const status = optional("repositoryStatus");
  if (!select || !status) return;
  const repositories = data.repositories || state.repositories || [];
  state.repositories = repositories;
  state.activeRepository = data.activeRepository || state.activeRepository || null;
  state.repositoryMode = Boolean(data.repositoryMode);

  select.innerHTML = "";
  if (!repositories.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = state.repositoryMode ? "저장소 없음" : "현재 워크스페이스";
    select.appendChild(option);
  } else {
    if (!state.activeRepository) {
      const legacy = document.createElement("option");
      legacy.value = "";
      legacy.textContent = "현재 워크스페이스";
      select.appendChild(legacy);
    }
    for (const repository of repositories) {
      const option = document.createElement("option");
      option.value = repository.name;
      option.textContent = repository.name;
      select.appendChild(option);
    }
  }
  select.value = state.activeRepository || "";

  const active = repositories.find((item) => item.name === state.activeRepository);
  const branch = active?.branch || (state.activeRepository ? "branch 없음" : "legacy");
  const count = active?.problemCount ?? data.problemCount ?? 0;
  const remote = active?.remote || (state.activeRepository ? "remote 없음" : data.workspace || "");
  status.innerHTML = `
    <div><strong>${escapeHtml(state.activeRepository || "현재 워크스페이스")}</strong></div>
    <div>${escapeHtml(branch)} · ${count}개 문제</div>
    <div title="${escapeHtml(remote)}">${escapeHtml(remote)}</div>
  `;
}
/**
 * 문제 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {Array} problems 문제을 계산하거나 검증할 때 필요한 문제 입력입니다.
 */
export function renderProblems(problems) {
  state.problems = problems;
  const list = $("problemList");
  list.innerHTML = "";
  if (!problems.length) {
    list.textContent = "등록된 문제가 없습니다.";
    list.classList.add("muted");
    return;
  }
  list.classList.remove("muted");
  const grouped = new Map();
  for (const problem of problems) {
    const folder = folderLabel(problem.folder);
    if (!grouped.has(folder)) grouped.set(folder, []);
    grouped.get(folder).push(problem);
  }
  for (const [folder, folderProblems] of grouped) {
    const collapsed = isProblemFolderCollapsed(folder);
    const section = document.createElement("section");
    section.className = "problem-folder-section";
    section.classList.toggle("collapsed", collapsed);
    const heading = document.createElement("div");
    heading.className = "problem-folder-row";
    heading.innerHTML = `
      <button
        class="problem-folder"
        type="button"
        aria-expanded="${collapsed ? "false" : "true"}"
        aria-label="${escapeHtml(folder)} 폴더 ${collapsed ? "펼치기" : "접기"}"
      >
        <span class="problem-folder-label">${escapeHtml(folder)}</span>
        <span class="problem-folder-count">${folderProblems.length}</span>
      </button>
    `;
    heading.querySelector(".problem-folder").addEventListener("click", () => {
      toggleProblemFolder(folder);
    });
    section.appendChild(heading);
    list.appendChild(section);
    if (collapsed) continue;
    for (const problem of folderProblems) {
      const item = document.createElement("button");
      const validationStatus = problemValidationStatus(problem);
      item.className = ["list-item", validationStatus?.className].filter(Boolean).join(" ");
      item.type = "button";
      if (validationStatus?.title) item.title = validationStatus.title;
      item.innerHTML = `
        <span class="problem-title-row">
          <strong>${escapeHtml(problemLabel(problem))}</strong>
          ${
            validationStatus
              ? `<span class="problem-status-badge ${escapeHtml(validationStatus.badgeClass)}">${escapeHtml(validationStatus.label)}</span>`
              : ""
          }
        </span>
        <span class="problem-meta-row">${escapeHtml(problem.defaultProfile || "hidden")} · v${escapeHtml(problem.version || "-")}</span>
      `;
      item.classList.toggle("active", problem.problemId === state.selectedProblem);
      if (problem.problemId === state.selectedProblem) item.setAttribute("aria-current", "page");
      item.addEventListener("click", () => {
        void workspaceCallbacks.withErrors(
          () => workspaceCallbacks.selectProblem(problem.problemId),
          "문제를 불러오는 중입니다."
        );
        closeSidebar();
      });
      section.appendChild(item);
    }
  }
}
