const app = window.AljApp;
const { state } = app;

/**
 * formatSavedAt 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} savedAt `savedAt` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function formatSavedAt(savedAt) {
  if (!savedAt) return "saved source";
  return new Date(savedAt * 1000).toLocaleString();
}

/**
 * sourceMatchesHistoryFilters 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} source `source` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function sourceMatchesHistoryFilters(source) {
  const query = String(state.sourceHistoryFilter || "").trim().toLowerCase();
  const statusFilter = state.sourceHistoryStatusFilter || "all";
  const status = source.lastRun?.status || "";
  if (statusFilter !== "all" && status !== statusFilter) return false;
  if (!query) return true;
  return [
    source.filename,
    source.problemId,
    source.language,
    status.replaceAll("_", " "),
    status,
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(query));
}

/**
 * renderSourceHistory 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} data 처리할 데이터입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function renderSourceHistory(data) {
  const list = app.optional("sourceHistoryList");
  if (!list) return;
  const allSources = data?.sources || [];
  state.sources = allSources;
  const problemSources = state.selectedProblem
    ? allSources.filter((source) => source.problemId === state.selectedProblem)
    : allSources;
  const filterInput = app.optional("sourceHistoryFilterInput");
  const statusInput = app.optional("sourceHistoryStatusFilter");
  if (filterInput && filterInput.value !== state.sourceHistoryFilter) {
    filterInput.value = state.sourceHistoryFilter;
  }
  if (statusInput && statusInput.value !== state.sourceHistoryStatusFilter) {
    statusInput.value = state.sourceHistoryStatusFilter;
  }
  const sources = problemSources.filter(sourceMatchesHistoryFilters);
  list.innerHTML = "";
  if (!sources.length) {
    const hasActiveFilter =
      Boolean(state.sourceHistoryFilter) || state.sourceHistoryStatusFilter !== "all";
    list.textContent = hasActiveFilter
      ? "No cached sources match filters."
      : allSources.length
        ? "No cached sources for this problem."
        : "No cached sources.";
    list.classList.add("muted");
    return;
  }
  list.classList.remove("muted");
  for (const source of sources) {
    const item = document.createElement("article");
    item.className = "source-history-item";

    const text = document.createElement("div");
    text.className = "source-history-text";
    const title = document.createElement("strong");
    title.textContent = source.filename || "source";
    const meta = document.createElement("span");
    const status = source.lastRun?.status ? ` · ${source.lastRun.status.replaceAll("_", " ")}` : "";
    meta.textContent = `${source.problemId || "unknown"} · ${source.language || "Unknown"} · ${
      source.sizeLabel || "0 B"
    }${status} · ${formatSavedAt(source.savedAt)}`;
    text.appendChild(title);
    text.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "source-history-actions";

    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.textContent = "Use Code";
    openButton.addEventListener("click", () => {
      void app.withErrors(() => loadCachedSource(source.sourceId));
    });

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "danger";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", () => {
      void app.withErrors(() => deleteCachedSource(source.sourceId, source.filename || "source"));
    });

    actions.appendChild(openButton);
    actions.appendChild(deleteButton);

    item.appendChild(text);
    item.appendChild(actions);
    list.appendChild(item);
  }
}

/**
 * refreshSourceHistory 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
async function refreshSourceHistory() {
  const data = await app.api("/api/sources");
  renderSourceHistory(data);
}

/**
 * loadCachedSource 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} sourceId `sourceId` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function loadCachedSource(sourceId) {
  const source = await app.api(`/api/sources/${encodeURIComponent(sourceId)}`);
  if (source.problemId && state.problems.some((problem) => problem.problemId === source.problemId)) {
    state.selectedProblem = source.problemId;
    app.$("problemSelect").value = source.problemId;
    app.renderProblemSelection();
    await app.loadSamples();
  }
  app.setMode("text");
  app.$("filenameInput").value = source.filename || "";
  app.$("sourceTextInput").value = source.sourceText || "";
  app.updateLanguageBadge();
  app.updateEditorView();
  app.syncEditorScroll();
  if (source.lastRunResult) {
    await app.restoreRunResult(source.lastRunResult);
  } else {
    app.resetRunStatus("Cached source loaded. No previous run result.");
  }
  app.showToast(`Cached source loaded: ${source.filename || sourceId}`);
}

/**
 * deleteCachedSource 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} sourceId `sourceId` 값입니다.
 * @param {any} filename `filename` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function deleteCachedSource(sourceId, filename) {
  await app.api(`/api/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
  app.showToast(`Cached source deleted: ${filename}`);
  await app.refreshSecondaryData();
}

/**
 * updateSourceHistoryFilter 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function updateSourceHistoryFilter() {
  state.sourceHistoryFilter = app.optional("sourceHistoryFilterInput")?.value || "";
  state.sourceHistoryStatusFilter = app.optional("sourceHistoryStatusFilter")?.value || "all";
  renderSourceHistory({ sources: state.sources });
}

Object.assign(app, {
  deleteCachedSource,
  formatSavedAt,
  loadCachedSource,
  refreshSourceHistory,
  renderSourceHistory,
  updateSourceHistoryFilter,
});
