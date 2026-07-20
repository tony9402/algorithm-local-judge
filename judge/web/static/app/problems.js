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
  const list = app.optional("problemList");
  const currentToggle = problemFolderToggle(folder);
  const anchorOffset = list && currentToggle
    ? currentToggle.getBoundingClientRect().top - list.getBoundingClientRect().top
    : null;
  const collapsed = collapsedFolders();
  if (collapsed.has(folder)) collapsed.delete(folder);
  else collapsed.add(folder);
  rememberCollapsedFolders(collapsed);
  renderProblems(state.problems, {
    scrollAnchor: anchorOffset === null ? null : { folder, offset: anchorOffset },
  });
}

function problemFolderToggle(folder) {
  return [...(app.optional("problemList")?.querySelectorAll("[data-folder-toggle]") || [])]
    .find((item) => item.getAttribute("data-folder-toggle") === folder) || null;
}

function captureProblemListState(list) {
  const focused = document.activeElement;
  const stateSnapshot = {
    focusedFolder: null,
    focusedList: focused === list,
    focusedProblemId: null,
    hadItems: Boolean(list.querySelector("[data-problem-id]")),
    scrollTop: list.scrollTop,
  };
  if (focused instanceof HTMLElement && list.contains(focused)) {
    stateSnapshot.focusedProblemId = focused.closest("[data-problem-id]")?.dataset.problemId || null;
    stateSnapshot.focusedFolder = focused.closest("[data-folder-toggle]")
      ?.getAttribute("data-folder-toggle") ?? null;
  }
  return stateSnapshot;
}

function problemItem(problemId) {
  return [...(app.optional("problemList")?.querySelectorAll("[data-problem-id]") || [])]
    .find((item) => item.dataset.problemId === problemId) || null;
}

function ensureProblemItemVisible(item) {
  const list = app.optional("problemList");
  if (!list || !item) return;
  const overflow = window.getComputedStyle(list).overflowY;
  if (overflow !== "auto" && overflow !== "scroll") return;
  const listRect = list.getBoundingClientRect();
  const itemRect = item.getBoundingClientRect();
  if (itemRect.top < listRect.top || itemRect.bottom > listRect.bottom) {
    item.scrollIntoView({ block: "nearest" });
  }
}

function restoreProblemListState(list, snapshot, { resetScroll = false, scrollAnchor = null } = {}) {
  list.scrollTop = resetScroll ? 0 : snapshot.scrollTop;
  if (!resetScroll && scrollAnchor) {
    const toggle = problemFolderToggle(scrollAnchor.folder);
    if (toggle) {
      const nextOffset = toggle.getBoundingClientRect().top - list.getBoundingClientRect().top;
      list.scrollTop += nextOffset - scrollAnchor.offset;
    }
  }
  let focusTarget = null;
  if (snapshot.focusedProblemId) focusTarget = problemItem(snapshot.focusedProblemId);
  else if (snapshot.focusedFolder !== null) focusTarget = problemFolderToggle(snapshot.focusedFolder);
  else if (snapshot.focusedList) focusTarget = list;
  if (focusTarget instanceof HTMLElement) {
    focusTarget.focus({ preventScroll: true });
    if (focusTarget !== list) ensureProblemItemVisible(focusTarget);
  }
}

function autoScrollProblemList(event) {
  const list = app.optional("problemList");
  if (!list || list.scrollHeight <= list.clientHeight) return;
  const rect = list.getBoundingClientRect();
  const edge = Math.min(56, rect.height / 4);
  if (event.clientY < rect.top + edge) list.scrollTop -= 18;
  else if (event.clientY > rect.bottom - edge) list.scrollTop += 18;
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

function problemMatchesSearch(problem, query) {
  const normalizedQuery = String(query || "").trim().toLowerCase();
  if (!normalizedQuery) return true;
  return [
    problem.problemId,
    problem.title,
    problemFolder(problem),
  ].filter(Boolean).some((value) => String(value).toLowerCase().includes(normalizedQuery));
}

function filterProblems(problems, query = state.problemSearch) {
  return problems.filter((problem) => problemMatchesSearch(problem, query));
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
  button.title = "새 폴더를 만든 뒤 선택한 문제의 폴더 이동 메뉴에서 사용할 수 있습니다.";
}
function problemFolderValues(problem) {
  const values = new Set([""]);
  for (const folder of state.folders || []) {
    values.add(String(typeof folder === "string" ? folder : folder.folder || "").trim());
  }
  values.add(problemFolder(problem));
  return [...values].sort((left, right) =>
    problemFolderLabel(left).localeCompare(problemFolderLabel(right))
  );
}

let problemFolderMoveContext = null;

function folderMoveAction(problemId, container = document) {
  return [...container.querySelectorAll("[data-folder-move-problem]")]
    .find((element) => element.dataset.folderMoveProblem === problemId) || null;
}

function renderProblemFolderMoveDialog(problem) {
  const label = app.$("problemFolderMoveProblemLabel");
  const select = app.$("problemFolderMoveSelect");
  label.textContent = `${problem.problemId} ${problem.title || ""}`.trim();
  select.innerHTML = "";
  for (const folder of problemFolderValues(problem)) {
    const option = document.createElement("option");
    option.value = folder;
    option.textContent = problemFolderLabel(folder);
    select.appendChild(option);
  }
  select.value = problemFolder(problem);
  select.dataset.currentFolder = problemFolder(problem);
  app.$("problemFolderMoveConfirmButton").disabled = true;
}

function openProblemFolderMove(problemId, trigger) {
  const problem = state.problems.find((item) => item.problemId === problemId);
  if (!problem?.folderEditable || problem.problemId !== state.selectedProblem) return;
  const fromPicker = Boolean(trigger?.closest("#problemPickerModal"));
  problemFolderMoveContext = { fromPicker, problemId };
  if (fromPicker) app.closeModals();
  renderProblemFolderMoveDialog(problem);
  app.openModal("problemFolderMoveModal");
}

function onProblemFolderMoveClosed() {
  const context = problemFolderMoveContext;
  problemFolderMoveContext = null;
  if (!context?.fromPicker) return;
  window.setTimeout(() => {
    if (!window.matchMedia("(max-width: 900px)").matches) return;
    renderProblemPicker(state.problems);
    app.openModal("problemPickerModal");
    window.setTimeout(() => {
      const list = app.optional("problemPickerList");
      if (list) folderMoveAction(context.problemId, list)?.focus({ preventScroll: true });
    }, 0);
  }, 0);
}

async function submitProblemFolderMove() {
  const context = problemFolderMoveContext;
  if (!context) return;
  const folder = app.$("problemFolderMoveSelect").value;
  await updateProblemFolder(context.problemId, folder, {
    closeMoveDialog: true,
    restoreMoveFocus: !context.fromPicker,
  });
}

async function chooseProblem(problemId, options = {}) {
  const select = app.$("problemSelect");
  select.value = problemId;
  await handleProblemChange(options);
  await app.refreshRecentSubmissions?.();
}

function createProblemFolderMoveAction(problem) {
  const moveButton = document.createElement("button");
  moveButton.className = "problem-folder-move-action";
  moveButton.type = "button";
  moveButton.dataset.folderMoveProblem = problem.problemId;
  moveButton.setAttribute("aria-label", `${problem.problemId} 문제 폴더 이동`);
  moveButton.title = "폴더 이동";
  moveButton.textContent = "이동";
  moveButton.addEventListener("click", () => openProblemFolderMove(problem.problemId, moveButton));
  return moveButton;
}

function createProblemItem(problem, { picker = false } = {}) {
  const row = document.createElement("div");
  row.className = "problem-item-row";
  const item = document.createElement("button");
  item.className = "list-item";
  item.type = "button";
  item.dataset.problemId = problem.problemId;
  item.dataset.folder = problemFolder(problem);
  item.draggable = Boolean(problem.folderEditable && !picker);
  item.setAttribute("aria-pressed", "false");
  if (problem.folderEditable && !picker) {
    item.setAttribute("aria-describedby", "problemDragHelp");
    item.setAttribute("aria-grabbed", "false");
    item.title = "드래그하거나 옆의 이동 버튼으로 폴더를 변경할 수 있습니다.";
  }
  const label = document.createElement("strong");
  label.textContent = `${problem.problemId} ${problem.title || ""}`;
  const meta = document.createElement("span");
  meta.textContent = problem.folderEditable
    ? `v${problem.version ?? ""}`
    : `v${problem.version ?? ""} · 읽기 전용`;
  item.append(label, meta);
  item.addEventListener("click", () => {
    void app.withErrors(() => chooseProblem(problem.problemId, {
      closePicker: picker,
      focusEditor: picker,
    }));
  });
  item.addEventListener("dragstart", (event) => {
    if (!problem.folderEditable) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", problem.problemId);
    item.setAttribute("aria-grabbed", "true");
    item.classList.add("dragging");
  });
  item.addEventListener("dragend", () => {
    item.setAttribute("aria-grabbed", "false");
    item.classList.remove("dragging");
  });
  row.appendChild(item);
  if (problem.folderEditable && problem.problemId === state.selectedProblem) {
    row.classList.add("has-folder-action");
    row.appendChild(createProblemFolderMoveAction(problem));
  }
  return row;
}
function createProblemFolderGroup(folder, problems, { picker = false } = {}) {
  const group = document.createElement("section");
  group.className = picker ? "problem-picker-group" : "problem-folder-group";
  group.dataset.folder = folder;
  const collapsed = !picker && collapsedFolders().has(folder);
  group.classList.toggle("collapsed", collapsed);
  if (picker) {
    group.innerHTML = `
      <div class="problem-folder-header problem-picker-folder-header">
        <strong>${app.escapeHtml(problemFolderLabel(folder))}</strong>
        <small>${problems.length}</small>
      </div>
    `;
  } else {
    const canDelete = Boolean(folder);
    group.innerHTML = `
      <div class="problem-folder-header">
        <button class="folder-toggle" type="button" data-folder-toggle="${app.escapeHtml(folder)}" aria-expanded="${String(!collapsed)}" aria-label="${app.escapeHtml(problemFolderLabel(folder))}, ${problems.length}개 문제, ${collapsed ? "열기" : "접기"}">
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
  }
  const items = document.createElement("div");
  items.className = "problem-folder-items";
  items.classList.toggle("hidden", collapsed);
  for (const problem of problems) {
    items.appendChild(createProblemItem(problem, { picker }));
  }
  if (!problems.length) {
    const empty = document.createElement("div");
    empty.className = "muted empty-folder";
    empty.textContent = "비어 있는 폴더";
    items.appendChild(empty);
  }
  group.appendChild(items);
  group.addEventListener("dragover", (event) => {
    if (picker) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    group.classList.add("drag-over");
    autoScrollProblemList(event);
  });
  group.addEventListener("dragleave", () => group.classList.remove("drag-over"));
  group.addEventListener("drop", (event) => {
    if (picker) return;
    event.preventDefault();
    group.classList.remove("drag-over");
    const problemId = event.dataTransfer.getData("text/plain");
    if (problemId) void app.withErrors(() => updateProblemFolder(problemId, folder));
  });
  return group;
}

function syncProblemSearchInputs() {
  for (const inputId of ["problemSearchInput", "problemPickerSearchInput"]) {
    const input = app.optional(inputId);
    if (input && input.value !== state.problemSearch) input.value = state.problemSearch || "";
  }
}

function renderProblemPicker(problems) {
  const list = app.optional("problemPickerList");
  if (!list) return;
  list.innerHTML = "";
  const visibleProblems = filterProblems(problems);
  app.setText(
    "problemPickerResults",
    problems.length ? `${visibleProblems.length}개 문제 검색됨` : "설치된 문제가 없습니다."
  );
  if (!visibleProblems.length) {
    list.textContent = problems.length ? "검색 결과가 없습니다." : "설치된 문제가 없습니다.";
    list.classList.add("muted");
    return;
  }
  list.classList.remove("muted");
  for (const [folder, items] of problemsByFolder(visibleProblems)) {
    if (items.length) {
      list.appendChild(createProblemFolderGroup(folder, items, { picker: true }));
    }
  }
}

function problemPickerIsOpen() {
  const modal = app.optional("problemPickerModal");
  return Boolean(modal && !modal.classList.contains("hidden"));
}

function onProblemPickerClosed() {
  const list = app.optional("problemPickerList");
  if (list) list.innerHTML = "";
}
/**
 * 문제 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {Array} problems 문제을 계산하거나 검증할 때 필요한 문제 입력입니다.
 */
function renderProblems(problems, options = {}) {
  const list = app.$("problemList");
  const listState = captureProblemListState(list);
  state.problems = problems;
  document.body.classList.toggle("has-problems", problems.length > 0);
  const select = app.$("problemSelect");
  syncProblemSearchInputs();
  list.innerHTML = "";
  select.innerHTML = "";
  if (!problems.length) {
    state.selectedProblem = null;
    rememberProblemId(null);
    list.textContent = "설치된 문제가 없습니다.";
    list.classList.add("muted");
    renderProblemFolderControls();
    if (problemPickerIsOpen()) renderProblemPicker(problems);
    app.renderSamples(null);
    app.updateActionState();
    restoreProblemListState(list, listState, options);
    return;
  }
  list.classList.remove("muted");
  if (!state.selectedProblem || !problems.some((problem) => problem.problemId === state.selectedProblem)) {
    const preferred = urlProblemId() || storedProblemId();
    state.selectedProblem = problems.some((problem) => problem.problemId === preferred)
      ? preferred
      : problems[0].problemId;
  }
  const visibleProblems = filterProblems(problems);
  if (!visibleProblems.length) {
    list.textContent = "검색 결과가 없습니다.";
    list.classList.add("muted");
  } else {
    for (const [folder, items] of problemsByFolder(visibleProblems)) {
      list.appendChild(createProblemFolderGroup(folder, items));
    }
  }
  for (const problem of problems) {
    const option = document.createElement("option");
    option.value = problem.problemId;
    option.textContent = `${problem.problemId} ${problem.title || ""}`;
    select.appendChild(option);
  }
  select.value = state.selectedProblem;
  rememberProblemId(state.selectedProblem);
  if (problemPickerIsOpen()) renderProblemPicker(problems);
  renderProblemSelection();
  restoreProblemListState(list, listState, options);
  if (!listState.hadItems && !options.resetScroll) {
    ensureProblemItemVisible(problemItem(state.selectedProblem));
  }
}
/**
 * 문제 selection 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 */
function renderProblemSelection({ ensureVisible = false } = {}) {
  const problemId = state.selectedProblem;
  const problem = state.problems.find((item) => item.problemId === problemId);
  renderRunProfiles(problem);
  const selectionLists = [app.$("problemList"), app.optional("problemPickerList")].filter(Boolean);
  for (const list of selectionLists) {
    for (const item of list.querySelectorAll(".list-item")) {
      const isActive = item.dataset.problemId === problemId;
      item.classList.toggle("active", isActive);
      item.setAttribute("aria-pressed", String(isActive));
      const row = item.closest(".problem-item-row");
      const existingAction = row?.querySelector("[data-folder-move-problem]");
      if (!isActive || !problem?.folderEditable) {
        existingAction?.remove();
        row?.classList.remove("has-folder-action");
      } else if (row && !existingAction) {
        row.classList.add("has-folder-action");
        row.appendChild(createProblemFolderMoveAction(problem));
      }
    }
  }
  if (ensureVisible) ensureProblemItemVisible(problemItem(problemId));
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
    option.textContent = app.profileLabel(profile);
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
async function handleProblemChange({ closePicker = false, focusEditor = false } = {}) {
  const previousProblem = state.selectedProblem;
  saveProblemDraft(previousProblem);
  const problemId = app.$("problemSelect").value;
  state.selectedProblem = problemId;
  rememberProblemId(problemId);
  renderProblemSelection({ ensureVisible: true });
  restoreProblemDraft(problemId);
  state.artifacts = null;
  app.$("wrongPanel").classList.add("hidden");
  app.renderSourceHistory({ sources: state.sources });
  app.resetRunStatus(`문제를 변경했습니다. ${app.profileLabel(app.judgeProfile())} 테스트케이스를 채점에 사용합니다.`);
  await app.loadSamples();
  if (closePicker) app.closeModals();
  if (focusEditor) app.optional("sourceTextInput")?.focus();
}

function updateProblemSearch(value = app.optional("problemSearchInput")?.value || "") {
  state.problemSearch = value;
  renderProblems(state.problems, { resetScroll: true });
}

function openProblemNavigation() {
  if (window.matchMedia("(max-width: 900px)").matches) {
    syncProblemSearchInputs();
    renderProblemPicker(state.problems);
    app.openModal("problemPickerModal");
    return;
  }
  const target = app.optional("problemSearchInput") || app.optional("problemList");
  target?.scrollIntoView({ block: "start", behavior: "smooth" });
  target?.focus();
}
/**
 * 문제 폴더 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 *
 * @param {string} problemId 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
 * @param {any} folder 문제 폴더을 계산하거나 검증할 때 필요한 폴더 입력입니다.
 */
async function updateProblemFolder(problemId, folder, options = {}) {
  const currentProblem = state.problems.find((problem) => problem.problemId === problemId);
  const normalizedFolder = String(folder || "").trim();
  if (currentProblem && problemFolder(currentProblem) === normalizedFolder) {
    app.showToast(`${problemId} 문제는 이미 ${problemFolderLabel(normalizedFolder)} 폴더에 있습니다.`);
    return;
  }
  const restoreMoveFocus = Boolean(options.restoreMoveFocus)
    || (document.activeElement instanceof HTMLElement
      && document.activeElement.dataset.folderMoveProblem === problemId);
  const result = await app.api(`/api/problems/${encodeURIComponent(problemId)}/folder`, {
    method: "PATCH",
    body: JSON.stringify({ folder: normalizedFolder }),
  });
  state.problems = state.problems.map((problem) =>
    problem.problemId === problemId
      ? { ...problem, folder: result.folder, folderEditable: result.folderEditable }
      : problem
  );
  if (options.closeMoveDialog) app.closeModals();
  renderProblems(state.problems);
  if (restoreMoveFocus) {
    const container = app.optional("problemList");
    if (container) folderMoveAction(problemId, container)?.focus({ preventScroll: true });
  }
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
  if (problems.length) {
    const names = problems.map((problem) => problem.problemId).join(", ");
    const confirmed = window.confirm(
      `${problemFolderLabel(folder)} 폴더를 삭제합니다.\n`
      + `폴더 내 문제는 삭제하지 않고 미분류로 옮깁니다.\n`
      + `옮겨질 문제: ${names}`
    );
    if (!confirmed) return;
  }
  const result = await app.api("/api/folders", {
    method: "DELETE",
    body: JSON.stringify({ folder, mode: "move_to_uncategorized" }),
  });
  state.folders = result.folders || [];
  await app.refresh();
  const movedCount = result.movedProblems?.length || 0;
  const suffix = movedCount ? ` 문제 ${movedCount}개는 미분류로 옮겼습니다.` : "";
  app.showToast(`${problemFolderLabel(folder)} 폴더를 삭제했습니다.${suffix}`);
}

Object.assign(app, {
  createProblemFolderFromInput,
  deleteProblemFolder,
  handleProblemChange,
  filterProblems,
  onProblemFolderMoveClosed,
  onProblemPickerClosed,
  openProblemFolderMove,
  openProblemNavigation,
  rememberProblemId,
  problemFolderLabel,
  problemSupportsProfile,
  renderProblemSelection,
  renderRunProfiles,
  renderProblems,
  renderProblemPicker,
  saveProblemDraft,
  toggleFolderCollapsed,
  submitProblemFolderMove,
  updateProblemFolder,
  updateProblemSearch,
  updateSelectedProblemFolder: createProblemFolderFromInput,
});
