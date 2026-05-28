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
  return folder || "Uncategorized";
}

function problemsByFolder(problems) {
  const groups = new Map();
  for (const problem of problems) {
    const folder = problemFolder(problem);
    if (!groups.has(folder)) groups.set(folder, []);
    groups.get(folder).push(problem);
  }
  return [...groups.entries()].sort(([left], [right]) =>
    problemFolderLabel(left).localeCompare(problemFolderLabel(right))
  );
}
/**
 * 문제 폴더 controls 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderProblemFolderControls() {
  const input = app.optional("problemFolderInput");
  const button = app.optional("problemFolderSaveButton");
  if (!input || !button) return;
  const problem = state.problems.find((item) => item.problemId === state.selectedProblem);
  const editable = Boolean(problem?.folderEditable);
  input.value = problemFolder(problem);
  input.disabled = !problem;
  button.disabled = !problem || !editable;
  button.title = editable
    ? "선택한 문제의 folder를 변경합니다."
    : "설치된 .aljpack 문제는 folder를 직접 변경할 수 없습니다.";
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
  const folderHint = problem.folderEditable ? "Drag to move folder" : "Read-only pack";
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
  group.innerHTML = `
    <div class="problem-folder-header">
      <span>${app.escapeHtml(problemFolderLabel(folder))}</span>
      <small>${problems.length}</small>
    </div>
  `;
  const items = document.createElement("div");
  items.className = "problem-folder-items";
  for (const problem of problems) items.appendChild(createProblemItem(problem, select));
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
  for (const [folder, items] of problemsByFolder(problems)) {
    list.appendChild(createProblemFolderGroup(folder, items, select));
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
/**
 * 문제 change 명령이나 이벤트를 받아 필요한 검증과 서비스 호출을 수행합니다.
 */
async function handleProblemChange() {
  const problemId = app.$("problemSelect").value;
  state.selectedProblem = problemId;
  rememberProblemId(problemId);
  renderProblemSelection();
  app.clearSourceInputs();
  state.artifacts = null;
  app.$("wrongPanel").classList.add("hidden");
  app.renderSourceHistory({ sources: state.sources });
  app.resetRunStatus(`Problem changed. ${app.judgeProfile()} cases will be used for Run.`);
  await app.loadSamples();
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
  app.showToast(`${problemId} folder moved to ${problemFolderLabel(result.folder)}.`);
}
/**
 * selected 문제 폴더 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
async function updateSelectedProblemFolder() {
  if (!state.selectedProblem) return;
  await updateProblemFolder(state.selectedProblem, app.$("problemFolderInput").value);
}

Object.assign(app, {
  handleProblemChange,
  rememberProblemId,
  problemFolderLabel,
  renderProblemSelection,
  renderRunProfiles,
  renderProblems,
  updateProblemFolder,
  updateSelectedProblemFolder,
});
