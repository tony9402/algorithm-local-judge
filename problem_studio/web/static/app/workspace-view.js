import { $, escapeHtml, optional, setText } from "./dom.js";
import { state } from "./state.js";
import { rememberView } from "./view-persistence.js";

const workspaceCallbacks = {
  selectProblem: async () => {},
  withErrors: async (action) => action(),
};

export function configureWorkspaceView(callbacks = {}) {
  Object.assign(workspaceCallbacks, callbacks);
}

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

export function setSidebarOpen(open) {
  document.body.classList.toggle("sidebar-open", open);
  optional("sidebarToggle")?.setAttribute("aria-expanded", open ? "true" : "false");
  updateMobileHeader();
}

export function toggleSidebar() {
  setSidebarOpen(!document.body.classList.contains("sidebar-open"));
}

export function closeSidebar() {
  setSidebarOpen(false);
}

export function problemLabel(problem) {
  return `${problem.problemId} ${problem.title || ""}`.trim();
}

export function folderLabel(folder) {
  return String(folder || "").trim() || "기본";
}

function problemFolderKey(folder) {
  return folderLabel(folder);
}

function isProblemFolderCollapsed(folder) {
  return state.problemFolderCollapsed[problemFolderKey(folder)] === true;
}

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
      item.className = "list-item";
      item.type = "button";
      item.innerHTML = `
        <strong>${escapeHtml(problemLabel(problem))}</strong>
        <span>${escapeHtml(problem.defaultProfile || "hidden")} · v${escapeHtml(problem.version || "-")}</span>
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
