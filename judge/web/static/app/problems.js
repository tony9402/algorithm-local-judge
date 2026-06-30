/**
 * 문제 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;
function storedProblemId() {
  try {
    return localStorage.getItem(app.SELECTED_PROBLEM_KEY);
  } catch {
    return null;
  }
}

function urlProblemId() {
  try {
    return new URL(window.location.href).searchParams.get("problem");
  } catch {
    return null;
  }
}
function rememberProblemInUrl(problemId) {
  try {
    const url = new URL(window.location.href);
    if (problemId) url.searchParams.set("problem", problemId);
    else url.searchParams.delete("problem");
    window.history.replaceState({}, "", url);
  } catch {
    // Older embedded browsers may restrict URL mutation; localStorage still preserves it.
  }
}
function rememberProblemId(problemId) {
  try {
    if (problemId) localStorage.setItem(app.SELECTED_PROBLEM_KEY, problemId);
    else localStorage.removeItem(app.SELECTED_PROBLEM_KEY);
  } catch {
    // Storage can be disabled in hardened browsers; selection still works in memory.
  }
  rememberProblemInUrl(problemId);
}

function problemFolder(problem) {
  return (problem?.folder || "").trim();
}

function problemFolderLabel(folder) {
  return folder || "미분류";
}

function collapsedFolders() {
  try {
    return new Set(JSON.parse(localStorage.getItem(app.COLLAPSED_FOLDERS_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function rememberCollapsedFolders(values) {
  try {
    localStorage.setItem(app.COLLAPSED_FOLDERS_KEY, JSON.stringify([...values]));
  } catch {
    // Folder collapse state is a convenience; rendering still works without storage.
  }
}

function toggleFolderCollapsed(folder) {
  const collapsed = collapsedFolders();
  if (collapsed.has(folder)) collapsed.delete(folder);
  else collapsed.add(folder);
  rememberCollapsedFolders(collapsed);
  renderProblems(state.problems);
}

function problemsByFolder(problems) {
  const groups = new Map();
  for (const folder of state.folders || []) {
    const value = typeof folder === "string" ? folder : folder.folder;
    groups.set((value || "").trim(), []);
  }
  for (const problem of problems) {
    const folder = problemFolder(problem);
    if (!groups.has(folder)) groups.set(folder, []);
    groups.get(folder).push(problem);
  }
  return [...groups.entries()].sort(([left], [right]) =>
    problemFolderLabel(left).localeCompare(problemFolderLabel(right))
  );
}

function problemMatchesSearch(problem) {
  const query = String(state.problemSearch || "").trim().toLowerCase();
  if (!query) return true;
  return [
    problem.problemId,
    problem.title,
    problemFolder(problem),
  ].filter(Boolean).some((value) => String(value).toLowerCase().includes(query));
}

function filteredProblems(problems) {
  return problems.filter(problemMatchesSearch);
}

function currentSourceDraft() {
  return {
    filename: app.optional("filenameInput")?.value || "",
    language: app.optional("languageHint")?.value || "",
    sourceText: app.optional("sourceTextInput")?.value || "",
    sourceMode: state.sourceMode || "text",
  };
}

function saveProblemDraft(problemId) {
  if (!problemId) return;
  state.problemDrafts[problemId] = currentSourceDraft();
}

function restoreProblemDraft(problemId) {
  const draft = state.problemDrafts[problemId];
  app.clearSourceInputs();
  if (!draft) return;
  app.setMode(draft.sourceMode || "text");
  const filenameInput = app.optional("filenameInput");
  const languageInput = app.optional("languageHint");
  const sourceInput = app.optional("sourceTextInput");
  if (filenameInput) filenameInput.value = draft.filename || "";
  if (languageInput && draft.language) languageInput.value = draft.language;
  if (sourceInput) sourceInput.value = draft.sourceText || "";
  app.updateLanguageBadge();
  app.updateEditorView();
  app.syncEditorScroll();
}

/**
 * 문제 폴더 controls 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderProblemFolderControls() {
  const input = app.optional("problemFolderInput");
  const button = app.optional("problemFolderSaveButton");
  if (!input || !button) return;
  button.disabled = state.isBusy || !input.value.trim();
  button.title = "새 폴더를 만든 뒤 문제를 드래그해서 옮깁니다.";
}
function createProblemItem(problem, select) {
  const item = document.createElement("button");
  item.className = "list-item";
  item.type = "button";
  item.dataset.problemId = problem.problemId;
  item.dataset.folder = problemFolder(problem);
  item.draggable = Boolean(problem.folderEditable);
  item.setAttribute("aria-pressed", "false");
  const problemLabel = `${app.escapeHtml(problem.problemId)} ${app.escapeHtml(problem.title || "")}`;
  const folderHint = problem.folderEditable ? "드래그해서 폴더 이동" : "읽기 전용";
  item.innerHTML = `<strong>${problemLabel}</strong><span>v${app.escapeHtml(problem.version ?? "")} · ${app.escapeHtml(folderHint)}</span>`;
  item.addEventListener("click", () => {
    select.value = problem.problemId;
    void app.withErrors(handleProblemChange);
  });
  item.addEventListener("dragstart", (event) => {
    if (!problem.folderEditable) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", problem.problemId);
    item.classList.add("dragging");
  });
  item.addEventListener("dragend", () => item.classList.remove("dragging"));
  return item;
}
function createProblemFolderGroup(folder, problems, select) {
  const group = document.createElement("section");
  group.className = "problem-folder-group";
  group.dataset.folder = folder;
  const collapsed = collapsedFolders().has(folder);
  group.classList.toggle("collapsed", collapsed);
  const canDelete = Boolean(folder);
  group.innerHTML = `
    <div class="problem-folder-header">
      <button class="folder-toggle" type="button" data-folder-toggle="${app.escapeHtml(folder)}" aria-expanded="${String(!collapsed)}">
        <span>${collapsed ? "▸" : "▾"}</span>
        <strong>${app.escapeHtml(problemFolderLabel(folder))}</strong>
      </button>
      <div class="folder-header-actions">
        <small>${problems.length}</small>
        ${
          canDelete
            ? `<button class="folder-delete" type="button" data-folder-delete="${app.escapeHtml(folder)}" aria-label="${app.escapeHtml(problemFolderLabel(folder))} 삭제">삭제</button>`
            : ""
        }
      </div>
    </div>
  `;
  const items = document.createElement("div");
  items.className = "problem-folder-items";
  items.classList.toggle("hidden", collapsed);
  for (const problem of problems) items.appendChild(createProblemItem(problem, select));
  if (!problems.length) {
    const empty = document.createElement("div");
    empty.className = "muted empty-folder";
    empty.textContent = "비어 있는 폴더";
    items.appendChild(empty);
  }
  group.appendChild(items);
  group.addEventListener("dragover", (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    group.classList.add("drag-over");
  });
  group.addEventListener("dragleave", () => group.classList.remove("drag-over"));
  group.addEventListener("drop", (event) => {
    event.preventDefault();
    group.classList.remove("drag-over");
    const problemId = event.dataTransfer.getData("text/plain");
    if (problemId) void app.withErrors(() => updateProblemFolder(problemId, folder));
  });
  return group;
}
/**
 * 문제 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {Array} problems 문제을 계산하거나 검증할 때 필요한 문제 입력입니다.
 */
function renderProblems(problems) {
  state.problems = problems;
  document.body.classList.toggle("has-problems", problems.length > 0);
  const list = app.$("problemList");
  const select = app.$("problemSelect");
  const searchInput = app.optional("problemSearchInput");
  if (searchInput && searchInput.value !== state.problemSearch) {
    searchInput.value = state.problemSearch || "";
  }
  list.innerHTML = "";
  select.innerHTML = "";
  if (!problems.length) {
    state.selectedProblem = null;
    rememberProblemId(null);
    list.textContent = "No problems installed.";
    list.classList.add("muted");
    renderProblemFolderControls();
    app.renderSamples(null);
    app.updateActionState();
    return;
  }
  list.classList.remove("muted");
  const visibleProblems = filteredProblems(problems);
  if (!visibleProblems.length) {
    list.textContent = "검색 결과가 없습니다.";
    list.classList.add("muted");
  } else {
    for (const [folder, items] of problemsByFolder(visibleProblems)) {
      list.appendChild(createProblemFolderGroup(folder, items, select));
    }
  }
  for (const problem of problems) {
    const option = document.createElement("option");
    option.value = problem.problemId;
    option.textContent = `${problem.problemId} ${problem.title || ""}`;
    select.appendChild(option);
  }
  if (!state.selectedProblem || !problems.some((problem) => problem.problemId === state.selectedProblem)) {
    const preferred = urlProblemId() || storedProblemId();
    state.selectedProblem = problems.some((problem) => problem.problemId === preferred)
      ? preferred
      : problems[0].problemId;
  }
  select.value = state.selectedProblem;
  rememberProblemId(state.selectedProblem);
  renderProblemSelection();
}
/**
 * 문제 selection 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderProblemSelection() {
  const problemId = state.selectedProblem;
  const problem = state.problems.find((item) => item.problemId === problemId);
  renderRunProfiles(problem);
  for (const item of app.$("problemList").querySelectorAll(".list-item")) {
    const isActive = item.dataset.problemId === problemId;
    item.classList.toggle("active", isActive);
    item.setAttribute("aria-pressed", String(isActive));
  }
  renderProblemFolderControls();
  app.updateActionState();
}
/**
 * 실행 프로필 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {any} problem 실행 프로필을 계산하거나 검증할 때 필요한 문제 입력입니다.
 */
function renderRunProfiles(problem) {
  const select = app.optional("runProfileSelect");
  if (!select) return;
  const current = state.config?.judgeProfile || "full";
  const profiles = problem?.profiles?.length ? problem.profiles : ["full", "sample", "hidden"];
  select.innerHTML = "";
  for (const profile of profiles) {
    const option = document.createElement("option");
    option.value = profile;
    option.textContent = profile === "full" ? "Full" : profile[0].toUpperCase() + profile.slice(1);
    select.appendChild(option);
  }
  select.value = profiles.includes(current) ? current : profiles[0];
  state.config.judgeProfile = select.value;
}

function problemSupportsProfile(profile) {
  const problem = state.problems.find((item) => item.problemId === state.selectedProblem);
  const profiles = problem?.profiles?.length ? problem.profiles : ["full", "sample", "hidden"];
  if (profile === "full") return true;
  return profiles.includes(profile);
}
/**
 * 문제 change 명령이나 이벤트를 받아 필요한 검증과 서비스 호출을 수행합니다.
 */
async function handleProblemChange() {
  const previousProblem = state.selectedProblem;
  saveProblemDraft(previousProblem);
  const problemId = app.$("problemSelect").value;
  state.selectedProblem = problemId;
  rememberProblemId(problemId);
  renderProblemSelection();
  restoreProblemDraft(problemId);
  state.artifacts = null;
  app.$("wrongPanel").classList.add("hidden");
  app.renderSourceHistory({ sources: state.sources });
  app.resetRunStatus(`문제를 변경했습니다. ${app.judgeProfile()} 케이스를 채점에 사용합니다.`);
  await app.loadSamples();
}

function updateProblemSearch() {
  state.problemSearch = app.optional("problemSearchInput")?.value || "";
  renderProblems(state.problems);
}
/**
 * 문제 폴더 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 *
 * @param {string} problemId 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
 * @param {any} folder 문제 폴더을 계산하거나 검증할 때 필요한 폴더 입력입니다.
 */
async function updateProblemFolder(problemId, folder) {
  const result = await app.api(`/api/problems/${encodeURIComponent(problemId)}/folder`, {
    method: "PATCH",
    body: JSON.stringify({ folder }),
  });
  state.problems = state.problems.map((problem) =>
    problem.problemId === problemId
      ? { ...problem, folder: result.folder, folderEditable: result.folderEditable }
      : problem
  );
  renderProblems(state.problems);
  app.showToast(`${problemId} 문제를 ${problemFolderLabel(result.folder)} 폴더로 옮겼습니다.`);
}
/**
 * 입력값으로 새 문제 폴더를 만들고 목록에 반영합니다.
 */
async function createProblemFolderFromInput() {
  const input = app.$("problemFolderInput");
  const folder = input.value.trim();
  if (!folder) return;
  const result = await app.api("/api/folders", {
    method: "POST",
    body: JSON.stringify({ folder }),
  });
  state.folders = result.folders || state.folders;
  input.value = "";
  renderProblems(state.problems);
  app.showToast(`폴더 생성: ${problemFolderLabel(result.folder)}`);
}

async function deleteProblemFolder(folder) {
  const problems = state.problems.filter((problem) => problemFolder(problem) === folder);
  let confirmDelete = false;
  if (problems.length) {
    const names = problems.map((problem) => problem.problemId).join(", ");
    confirmDelete = window.confirm(
      `${problemFolderLabel(folder)} 폴더를 삭제합니다.\n폴더 내 문제들이 모두 삭제됩니다.\n삭제될 문제: ${names}`
    );
    if (!confirmDelete) return;
  }
  const result = await app.api("/api/folders", {
    method: "DELETE",
    body: JSON.stringify({ folder, confirm_delete_problems: confirmDelete }),
  });
  state.folders = result.folders || [];
  if (result.deletedProblems?.includes(state.selectedProblem)) {
    state.selectedProblem = null;
    rememberProblemId(null);
  }
  await app.refresh();
  app.showToast(`${problemFolderLabel(folder)} 폴더를 삭제했습니다.`);
}

Object.assign(app, {
  createProblemFolderFromInput,
  deleteProblemFolder,
  handleProblemChange,
  rememberProblemId,
  problemFolderLabel,
  problemSupportsProfile,
  renderProblemSelection,
  renderRunProfiles,
  renderProblems,
  saveProblemDraft,
  toggleFolderCollapsed,
  updateProblemFolder,
  updateProblemSearch,
  updateSelectedProblemFolder: createProblemFolderFromInput,
});
