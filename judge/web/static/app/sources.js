/**
 * 소스 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;

function formatSavedAt(savedAt) {
  if (!savedAt) return "저장된 코드";
  return new Date(savedAt * 1000).toLocaleString();
}

function sourceStatusLabel(status) {
  return {
    accepted: "맞았습니다",
    wrong_answer: "오답",
    compile_error: "컴파일 오류",
    runtime_error: "런타임 오류",
    time_limit: "시간 초과",
    memory_limit: "메모리 초과",
  }[status] || (status ? `알 수 없는 상태 (${status})` : "상태 없음");
}
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
 * 소스 이력 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {object} data 파일, API 응답, UI 렌더링에 사용할 구조화된 데이터입니다.
 */
function renderSourceHistory(data) {
  const list = app.optional("sourceHistoryList");
  if (!list) return;
  const allSources = data?.sources || [];
  state.sources = allSources;
  const problemSources = state.sourceHistoryScope === "all"
    ? allSources
    : state.selectedProblem
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
  for (const button of document.querySelectorAll("[data-source-scope]")) {
    const active = button.getAttribute("data-source-scope") === (state.sourceHistoryScope || "problem");
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  const sources = problemSources.filter(sourceMatchesHistoryFilters);
  list.innerHTML = "";
  if (!sources.length) {
    const hasActiveFilter =
      Boolean(state.sourceHistoryFilter) || state.sourceHistoryStatusFilter !== "all";
    list.textContent = hasActiveFilter
        ? "필터와 일치하는 이전 캐시 코드가 없습니다."
        : allSources.length
        ? "현재 범위에 이전 캐시 코드가 없습니다."
        : "이전 캐시 코드가 없습니다.";
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
    title.textContent = source.filename || "코드";
    const meta = document.createElement("span");
    const status = source.lastRun?.status ? ` · ${sourceStatusLabel(source.lastRun.status)}` : "";
    meta.textContent = `${source.problemId || "알 수 없는 문제"} · ${source.language || "알 수 없는 언어"} · ${
      source.sizeLabel || "0 B"
    }${status} · ${formatSavedAt(source.savedAt)}`;
    text.appendChild(title);
    text.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "source-history-actions";

    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.textContent = "코드 사용";
    openButton.addEventListener("click", () => {
      void app.withErrors(() => loadCachedSource(source.sourceId));
    });

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "danger";
    deleteButton.textContent = "삭제";
    deleteButton.addEventListener("click", () => {
      void app.withErrors(() => deleteCachedSource(source.sourceId, source.filename || "코드"));
    });

    actions.appendChild(openButton);
    actions.appendChild(deleteButton);

    item.appendChild(text);
    item.appendChild(actions);
    list.appendChild(item);
  }
}
/**
 * 소스 이력 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 */
async function refreshSourceHistory() {
  const data = await app.api("/api/sources");
  renderSourceHistory(data);
}
/**
 * cached 소스을 파일이나 캐시에서 읽고 필요한 기본값을 적용합니다.
 *
 * @param {string} sourceId 소스 ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.
 */
async function loadCachedSource(sourceId) {
  const source = await app.api(`/api/sources/${encodeURIComponent(sourceId)}`);
  app.saveProblemDraft?.(state.selectedProblem);
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
  app.resetRunStatus("이전 캐시 코드를 불러왔습니다. 저장된 채점 결과가 없습니다.");
  }
  app.showToast(`이전 캐시 코드 불러옴: ${source.filename || sourceId}`);
}
/**
 * cached 소스 파일이나 상태 항목을 안전성 검사를 거쳐 제거합니다.
 *
 * @param {string} sourceId 소스 ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.
 * @param {any} filename 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.
 */
async function deleteCachedSource(sourceId, filename) {
  const confirmed = window.confirm(`${filename} 이전 캐시 코드를 삭제합니다.\n삭제한 코드는 다시 불러올 수 없습니다.`);
  if (!confirmed) return;
  await app.api(`/api/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
  app.showToast(`이전 캐시 코드 삭제됨: ${filename}`);
  await app.refreshSecondaryData();
}
/**
 * 소스 이력 filter 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updateSourceHistoryFilter() {
  state.sourceHistoryFilter = app.optional("sourceHistoryFilterInput")?.value || "";
  state.sourceHistoryStatusFilter = app.optional("sourceHistoryStatusFilter")?.value || "all";
  renderSourceHistory({ sources: state.sources });
}

function setSourceHistoryScope(scope) {
  state.sourceHistoryScope = scope === "all" ? "all" : "problem";
  renderSourceHistory({ sources: state.sources });
}

Object.assign(app, {
  deleteCachedSource,
  formatSavedAt,
  loadCachedSource,
  refreshSourceHistory,
  renderSourceHistory,
  setSourceHistoryScope,
  updateSourceHistoryFilter,
});
