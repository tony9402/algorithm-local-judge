const state = {
  problems: [],
  selectedProblem: null,
  sourceMode: "upload",
  artifacts: null,
  selectedArtifact: "input",
  cache: null,
  sources: [],
  debugLogs: [],
  generationProgress: { current: 0, total: 0 },
  sampleLoadToken: 0,
  sampleCache: {},
  isBusy: false,
  config: {
    sampleProfile: "sample",
    judgeProfile: "hidden",
    webDebug: false,
  },
};

const ARTIFACT_PREVIEW_LIMIT = 12000;

const optional = (id) => document.getElementById(id);
const $ = (id) => {
  const element = optional(id);
  if (!element) throw new Error(`Missing UI element: ${id}`);
  return element;
};

function setText(id, value) {
  const element = optional(id);
  if (element) element.textContent = value;
}

function setDisabled(id, isDisabled) {
  const element = optional(id);
  if (element) element.disabled = isDisabled;
}

function on(id, eventName, handler) {
  const element = optional(id);
  if (element) element.addEventListener(eventName, handler);
}

function setBusy(isBusy) {
  state.isBusy = isBusy;
  setDisabled("addProblemButton", isBusy);
  setDisabled("cacheManageButton", isBusy);
  setDisabled("cachePreviewButton", isBusy);
  setDisabled("cacheClearRunsButton", isBusy);
  setDisabled("cacheClearAllButton", isBusy);
  updateActionState();
  updatePackActionState();
}

function setBadge(label, className = "neutral") {
  setText("statusBadge", label);
  const badge = optional("statusBadge");
  if (badge) badge.className = `badge ${className}`;
}

function setStatusCard(key, value, meta = "-") {
  setText(`${key}StatusValue`, value);
  setText(`${key}StatusMeta`, meta);
}

function showToast(message, className = "success", timeoutMs = 2800) {
  const host = optional("toastHost");
  if (!host) return;
  const toast = document.createElement("div");
  toast.className = `toast ${className}`;
  toast.setAttribute("role", "status");
  toast.textContent = message;
  host.appendChild(toast);
  window.setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(-8px)";
    window.setTimeout(() => toast.remove(), 180);
  }, timeoutMs);
}

function sampleProfile() {
  return state.config?.sampleProfile || "sample";
}

function judgeProfile() {
  return state.config?.judgeProfile || "hidden";
}

function preferredTheme() {
  const saved = localStorage.getItem("alj-theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("alj-theme", theme);
  const button = optional("themeToggleButton");
  if (button) {
    button.textContent = theme === "dark" ? "Light" : "Dark";
    button.setAttribute("aria-pressed", String(theme === "dark"));
  }
}

function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}

function setSummary(message, className = "result-summary") {
  const summary = optional("resultSummary");
  if (!summary) {
    setText("resultOutput", message);
    return;
  }
  summary.textContent = message;
  summary.className = className;
}

function resetRunStatus(message = "Ready.") {
  setBadge("Idle", "neutral");
  setText("resultMeta", "No run yet.");
  setStatusCard("cases", "Idle", "Hidden cases.yml plan");
  setStatusCard("data", "Idle", "Hidden judge data");
  setStatusCard("judge", "Idle");
  setStatusCard("run", "-", "No run");
  hideGenerationProgress();
  setSummary(message, "result-summary muted");
}

function renderDebugLog() {
  const output = optional("resultOutput");
  if (!output) return;
  const debugToggle = optional("debugModeInput");
  const shouldShow = Boolean(state.config?.webDebug) && Boolean(debugToggle?.checked);
  output.textContent = state.debugLogs.join("\n");
  output.classList.toggle("hidden", !shouldShow);
}

function clearDebugLog() {
  state.debugLogs = [];
  renderDebugLog();
}

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    headers: isFormData
      ? { ...(options.headers || {}) }
      : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof body === "object" && body.detail ? body.detail : body;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return body;
}

async function apiResponse(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    headers: isFormData
      ? { ...(options.headers || {}) }
      : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok && response.status !== 304) {
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    const detail = typeof body === "object" && body.detail ? body.detail : body;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response;
}

function languageFromName(name) {
  const lowered = (name || "").toLowerCase();
  if (lowered.endsWith(".cpp") || lowered.endsWith(".cc") || lowered.endsWith(".cxx")) return "C++";
  if (lowered.endsWith(".py")) return "Python";
  if (lowered.endsWith(".java")) return "Java";
  return "Unknown";
}

function sourceTextReady() {
  const input = optional("sourceTextInput");
  return Boolean(input?.value.trim());
}

function sourceUploadReady() {
  return Boolean(optional("sourceFileInput")?.files[0]);
}

function hasSelectedProblem() {
  return Boolean(state.selectedProblem || optional("problemSelect")?.value);
}

function hasRunnableSource() {
  return state.sourceMode === "upload" ? sourceUploadReady() : sourceTextReady();
}

function sourceReadinessText() {
  if (!hasSelectedProblem()) return "Install a problem first";
  if (!hasRunnableSource()) {
    return state.sourceMode === "upload" ? "Source file needed" : "Source code needed";
  }
  return `${activeSourceName()} ready`;
}

function updateActionState() {
  const hasProblem = hasSelectedProblem();
  const hasSource = hasRunnableSource();
  setDisabled("casesCompileButton", state.isBusy || !hasProblem);
  setDisabled("generateButton", state.isBusy || !hasProblem);
  setDisabled("runButton", state.isBusy || !hasProblem || !hasSource);

  const readiness = optional("sourceReadiness");
  if (readiness) {
    readiness.textContent = sourceReadinessText();
    readiness.classList.toggle("ready", hasProblem && hasSource);
  }
}

function syncFilenamePlaceholder() {
  const input = optional("filenameInput");
  const hint = optional("languageHint");
  if (input && hint) input.placeholder = hint.value || "main.cpp";
}

function updateLanguageBadge() {
  const name =
    state.sourceMode === "upload"
      ? $("sourceFileInput").files[0]?.name || ""
      : $("filenameInput").value || $("languageHint").value;
  const language = name ? languageFromName(name) : "No source";
  setText("languageBadge", language);
  setText("editorFileLabel", name || "main.py");
  setText("editorLanguageLabel", language);
  updateCodeHighlight();
  updateActionState();
}

function activeSourceName() {
  if (state.sourceMode === "upload") return $("sourceFileInput").files[0]?.name || "source";
  return $("filenameInput").value.trim() || $("languageHint").value || "source";
}

function updateEditorLineNumbers() {
  const input = optional("sourceTextInput");
  const gutter = optional("sourceLineNumbers");
  if (!input || !gutter) return;
  const lineCount = Math.max(1, input.value.split("\n").length);
  const numbers = [];
  for (let index = 1; index <= lineCount; index += 1) {
    numbers.push(String(index));
  }
  gutter.textContent = numbers.join("\n");
}

function escapeHtml(value) {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function highlightToken(token, language) {
  const isComment = token.startsWith("//") || token.startsWith("/*") || token.startsWith("#");
  if (isComment) return `<span class="hl-comment">${token}</span>`;
  if (token.startsWith('"') || token.startsWith("'")) {
    return `<span class="hl-string">${token}</span>`;
  }
  if (/^\d/.test(token)) return `<span class="hl-number">${token}</span>`;
  return `<span class="hl-keyword">${token}</span>`;
}

function highlightCode(source, language) {
  const escaped = escapeHtml(source || " ");
  const commonNumber = "\\b\\d+(?:\\.\\d+)?\\b";
  const cppKeywords =
    "alignas|alignof|auto|bool|break|case|catch|char|class|const|constexpr|continue|decltype|default|delete|do|double|else|enum|explicit|extern|false|float|for|friend|if|inline|int|long|namespace|new|nullptr|operator|private|protected|public|return|short|signed|sizeof|static|struct|switch|template|this|throw|true|try|typedef|typename|using|void|while|vector|string|pair|map|set|queue|stack|priority_queue";
  const javaKeywords =
    "abstract|assert|boolean|break|byte|case|catch|char|class|const|continue|default|do|double|else|enum|extends|false|final|finally|float|for|if|implements|import|instanceof|int|interface|long|new|null|package|private|protected|public|return|short|static|super|switch|this|throw|throws|true|try|void|while|String|System";
  const pyKeywords =
    "False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield|print|range|len|int|str|list|dict|set|tuple";
  const languageKey = (language || "").toLowerCase();
  const keywordPattern = languageKey.includes("python")
    ? pyKeywords
    : languageKey.includes("java")
      ? javaKeywords
      : cppKeywords;
  const tokenPattern = languageKey.includes("python")
    ? new RegExp(
        `(#.*|"""[\\s\\S]*?"""|'''[\\s\\S]*?'''|"(?:\\\\.|[^"\\\\])*"|'(?:\\\\.|[^'\\\\])*'|\\b(?:${keywordPattern})\\b|${commonNumber})`,
        "g"
      )
    : new RegExp(
        `(//.*|/\\*[\\s\\S]*?\\*/|"(?:\\\\.|[^"\\\\])*"|'(?:\\\\.|[^'\\\\])*'|\\b(?:${keywordPattern})\\b|${commonNumber})`,
        "g"
      );
  return escaped.replace(tokenPattern, (token) => highlightToken(token, languageKey));
}

function updateCodeHighlight() {
  const input = optional("sourceTextInput");
  const highlight = optional("sourceHighlight");
  if (!input || !highlight) return;
  highlight.innerHTML = highlightCode(input.value, $("editorLanguageLabel").textContent);
}

function updateEditorView() {
  updateEditorLineNumbers();
  updateCodeHighlight();
}

function syncEditorScroll() {
  const input = optional("sourceTextInput");
  const gutter = optional("sourceLineNumbers");
  const highlight = optional("sourceHighlight");
  if (!input || !gutter) return;
  gutter.scrollTop = input.scrollTop;
  if (highlight) {
    highlight.scrollTop = input.scrollTop;
    highlight.scrollLeft = input.scrollLeft;
  }
}

function insertEditorText(text) {
  const input = $("sourceTextInput");
  const start = input.selectionStart;
  const end = input.selectionEnd;
  input.value = `${input.value.slice(0, start)}${text}${input.value.slice(end)}`;
  input.selectionStart = start + text.length;
  input.selectionEnd = start + text.length;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function clearSourceInputs() {
  const fileInput = optional("sourceFileInput");
  const filenameInput = optional("filenameInput");
  const sourceTextInput = optional("sourceTextInput");
  if (fileInput) fileInput.value = "";
  if (filenameInput) filenameInput.value = "";
  if (sourceTextInput) sourceTextInput.value = "";
  updateLanguageBadge();
  updateEditorView();
  syncEditorScroll();
}

function renderProblems(problems) {
  state.problems = problems;
  document.body.classList.toggle("has-problems", problems.length > 0);
  const list = $("problemList");
  const select = $("problemSelect");
  list.innerHTML = "";
  select.innerHTML = "";
  if (!problems.length) {
    state.selectedProblem = null;
    list.textContent = "No problems installed.";
    list.classList.add("muted");
    renderSamples(null);
    updateActionState();
    return;
  }
  list.classList.remove("muted");
  for (const problem of problems) {
    const item = document.createElement("button");
    item.className = "list-item";
    item.type = "button";
    item.dataset.problemId = problem.problemId;
    item.setAttribute("aria-pressed", "false");
    item.innerHTML = `<strong>${problem.problemId} ${problem.title || ""}</strong><span>v${problem.version ?? ""}</span>`;
    item.addEventListener("click", () => {
      select.value = problem.problemId;
      void withErrors(handleProblemChange);
    });
    list.appendChild(item);

    const option = document.createElement("option");
    option.value = problem.problemId;
    option.textContent = `${problem.problemId} ${problem.title || ""}`;
    select.appendChild(option);
  }
  if (!state.selectedProblem || !problems.some((problem) => problem.problemId === state.selectedProblem)) {
    state.selectedProblem = problems[0].problemId;
  }
  select.value = state.selectedProblem;
  renderProblemSelection();
}

function renderPacks(packs) {
  const list = $("packList");
  list.innerHTML = "";
  if (!packs.length) {
    list.textContent = "No problem packs installed.";
    list.classList.add("muted");
    return;
  }
  list.classList.remove("muted");
  for (const pack of packs) {
    const item = document.createElement("div");
    item.className = "list-item";
    const platforms = (pack.supportedPlatforms || []).join(", ");
    const problems = (pack.problems || []).join(", ");
    item.innerHTML = `<strong>${pack.packId} ${pack.version || ""}</strong><span>${platforms} · ${problems}</span>`;
    list.appendChild(item);
  }
}

function renderCache(cache) {
  state.cache = cache;
  const sources = cache.sources || { count: 0 };
  $("cacheSummary").innerHTML = `
    <div>Total ${cache.totalSizeLabel}</div>
    <div>Problem caches ${cache.problems.length}</div>
    <div>Runs ${cache.runs.count}</div>
    <div>Sources ${sources.count}</div>
  `;
  renderCacheModalSummary(cache);
}

function clearSampleCache(problemId = null) {
  if (problemId) {
    delete state.sampleCache[problemId];
    return;
  }
  state.sampleCache = {};
}

function renderCacheModalSummary(cache) {
  const summary = optional("cacheModalSummary");
  if (!cache || !summary) return;
  const sources = cache.sources || { count: 0, sizeLabel: "0 B" };
  summary.innerHTML = `
    <div class="status-card">
      <span>Total</span>
      <strong>${cache.totalSizeLabel}</strong>
      <small>Cache size</small>
    </div>
    <div class="status-card">
      <span>Problem Data</span>
      <strong>${cache.problems.length}</strong>
      <small>Generated caches</small>
    </div>
    <div class="status-card">
      <span>Runs</span>
      <strong>${cache.runs.count}</strong>
      <small>${cache.runs.sizeLabel || "0 B"}</small>
    </div>
    <div class="status-card">
      <span>Sources</span>
      <strong>${sources.count}</strong>
      <small>${sources.sizeLabel || "0 B"}</small>
    </div>
  `;
}

function formatSavedAt(savedAt) {
  if (!savedAt) return "saved source";
  return new Date(savedAt * 1000).toLocaleString();
}

function renderSourceHistory(data) {
  const list = optional("sourceHistoryList");
  if (!list) return;
  const allSources = data?.sources || [];
  state.sources = allSources;
  const sources = state.selectedProblem
    ? allSources.filter((source) => source.problemId === state.selectedProblem)
    : allSources;
  list.innerHTML = "";
  if (!sources.length) {
    list.textContent = allSources.length ? "No cached sources for this problem." : "No cached sources.";
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
      void withErrors(() => loadCachedSource(source.sourceId));
    });

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "danger";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", () => {
      void withErrors(() => deleteCachedSource(source.sourceId, source.filename || "source"));
    });

    actions.appendChild(openButton);
    actions.appendChild(deleteButton);

    item.appendChild(text);
    item.appendChild(actions);
    list.appendChild(item);
  }
}

async function refreshSourceHistory() {
  const data = await api("/api/sources");
  renderSourceHistory(data);
}

async function loadCachedSource(sourceId) {
  const source = await api(`/api/sources/${encodeURIComponent(sourceId)}`);
  if (source.problemId && state.problems.some((problem) => problem.problemId === source.problemId)) {
    state.selectedProblem = source.problemId;
    $("problemSelect").value = source.problemId;
    renderProblemSelection();
    await loadSamples();
  }
  setMode("text");
  $("filenameInput").value = source.filename || "";
  $("sourceTextInput").value = source.sourceText || "";
  updateLanguageBadge();
  updateEditorView();
  syncEditorScroll();
  if (source.lastRunResult) {
    await restoreRunResult(source.lastRunResult);
  } else {
    resetRunStatus("Cached source loaded. No previous run result.");
  }
  showToast(`Cached source loaded: ${source.filename || sourceId}`);
}

async function deleteCachedSource(sourceId, filename) {
  await api(`/api/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
  showToast(`Cached source deleted: ${filename}`);
  await refreshSecondaryData();
}

function renderProblemSelection() {
  const problemId = state.selectedProblem;
  for (const item of $("problemList").querySelectorAll(".list-item")) {
    const isActive = item.dataset.problemId === problemId;
    item.classList.toggle("active", isActive);
    item.setAttribute("aria-pressed", String(isActive));
  }
  updateActionState();
}

async function handleProblemChange() {
  const problemId = $("problemSelect").value;
  state.selectedProblem = problemId;
  renderProblemSelection();
  clearSourceInputs();
  state.artifacts = null;
  $("wrongPanel").classList.add("hidden");
  renderSourceHistory({ sources: state.sources });
  resetRunStatus("Problem changed. Hidden cases will be used for Run.");
  await loadSamples();
}

function renderSamples(data) {
  const container = optional("sampleCases");
  if (!container) return;
  container.innerHTML = "";
  container.removeAttribute("aria-busy");
  if (!data) {
    setText("sampleMeta", "No problem selected.");
    container.textContent = "No sample cases loaded.";
    container.classList.add("muted");
    return;
  }
  const source = data.cached ? "cache" : "generated";
  setText(
    "sampleMeta",
    `${data.caseCount} ${data.profile || sampleProfile()} case(s) · ${source} · ${data.label}`
  );
  if (!data.cases?.length) {
    container.textContent = "No sample cases declared.";
    container.classList.add("muted");
    return;
  }
  container.classList.remove("muted");
  for (const sample of data.cases) {
    const item = document.createElement("article");
    item.className = "sample-case";

    const title = document.createElement("div");
    title.className = "sample-case-title";
    title.textContent = `${sample.case} ${sample.name || ""}`.trim();
    item.appendChild(title);

    const grid = document.createElement("div");
    grid.className = "sample-artifacts";
    for (const [label, value] of [
      ["Input", sample.input],
      ["Expected", sample.expected],
    ]) {
      const block = document.createElement("div");
      block.className = "sample-artifact";
      const heading = document.createElement("span");
      heading.textContent = label;
      const pre = document.createElement("pre");
      pre.className = "output small";
      pre.textContent = value;
      block.appendChild(heading);
      block.appendChild(pre);
      grid.appendChild(block);
    }
    item.appendChild(grid);
    container.appendChild(item);
  }
}

function renderSampleLoading(problemId) {
  const container = optional("sampleCases");
  if (!container) return;
  setText("sampleMeta", `${problemId} sample 데이터를 준비하는 중...`);
  container.classList.remove("muted");
  container.setAttribute("aria-busy", "true");
  container.innerHTML = "";

  const loading = document.createElement("div");
  loading.className = "sample-loading";

  const spinner = document.createElement("span");
  spinner.className = "spinner";
  spinner.setAttribute("aria-hidden", "true");

  const text = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = "Sample 데이터를 불러오는 중";
  const detail = document.createElement("span");
  detail.textContent = "처음에는 데이터를 생성하고, 이후에는 캐시된 sample을 사용합니다.";
  text.appendChild(title);
  text.appendChild(detail);

  loading.appendChild(spinner);
  loading.appendChild(text);
  container.appendChild(loading);
}

async function loadSamples({ force = false } = {}) {
  if (!state.selectedProblem) {
    renderSamples(null);
    return;
  }
  const problemId = state.selectedProblem;
  const token = ++state.sampleLoadToken;
  const cached = !force ? state.sampleCache[problemId] : null;
  if (cached) {
    renderSamples({ ...cached.data, cached: true });
  } else {
    renderSampleLoading(problemId);
  }
  const query = force ? "?force=true" : "";
  const headers = {};
  if (cached?.etag && !force) headers["If-None-Match"] = cached.etag;
  const response = await apiResponse(
    `/api/problems/${encodeURIComponent(problemId)}/samples${query}`,
    { headers }
  );
  if (token !== state.sampleLoadToken || problemId !== state.selectedProblem) return;
  if (response.status === 304 && cached) {
    renderSamples({ ...cached.data, cached: true });
    return;
  }
  const result = await response.json();
  const etag = response.headers.get("etag") || result.etag;
  if (etag && !force) {
    state.sampleCache[problemId] = { etag, data: result };
  }
  if (token !== state.sampleLoadToken || problemId !== state.selectedProblem) return;
  renderSamples(result);
}

function configureDebugUi() {
  const toggle = optional("debugToggle");
  const input = optional("debugModeInput");
  const enabled = Boolean(state.config?.webDebug);
  if (toggle) toggle.classList.toggle("hidden", !enabled);
  if (input && !enabled) input.checked = false;
  renderDebugLog();
}

async function refresh() {
  setText("subtitle", "Connecting to local server");
  const [config, problems] = await Promise.all([api("/api/config"), api("/api/problems")]);
  state.config = { ...state.config, ...config };
  renderProblems(problems);
  configureDebugUi();
  const officialRepoInput = optional("officialRepoInput");
  if (officialRepoInput) {
    officialRepoInput.value = state.config?.officialRepository || "tony9402/algorithm-modules";
  }
  setText("subtitle", "Connected to local server");
  const samplePromise = state.selectedProblem ? loadSamples() : Promise.resolve();
  const secondaryPromise = refreshSecondaryData();
  await samplePromise;
  await secondaryPromise;
}

async function refreshSecondaryData() {
  try {
    const [packs, cache, sources] = await Promise.all([
      api("/api/packs"),
      api("/api/cache"),
      api("/api/sources"),
    ]);
    renderPacks(packs);
    renderCache(cache);
    renderSourceHistory(sources);
  } catch (error) {
    showError(error.message);
  }
}

async function uploadPack() {
  const file = $("packFileInput").files[0];
  if (!file) throw new Error("Problem pack file is required.");
  $("packStatus").textContent = "Installing uploaded pack...";
  $("packStatus").className = "modal-status";
  const formData = new FormData();
  formData.append("file", file);
  const result = await api("/api/packs/upload", {
    method: "POST",
    body: formData,
  });
  $("packStatus").textContent = `Installed: ${result.label}`;
  $("packStatus").className = "modal-status success";
  clearSampleCache();
  await refresh();
}

async function downloadOfficialPack() {
  const repository = $("officialRepoInput").value.trim();
  const assetName = $("packAssetInput").value.trim();
  $("packStatus").textContent = "Downloading official pack...";
  $("packStatus").className = "modal-status";
  const result = await api("/api/packs/download", {
    method: "POST",
    body: JSON.stringify({
      repository: repository || null,
      asset_name: assetName || null,
    }),
  });
  $("packStatus").textContent = `Installed: ${result.assetName || result.label}`;
  $("packStatus").className = "modal-status success";
  clearSampleCache();
  await refresh();
}

function formatCaseDiagnostic(diagnostic) {
  const line = diagnostic.line ? `:${diagnostic.line}` : "";
  const profile = diagnostic.profile ? `profile ${diagnostic.profile}, ` : "";
  const location = diagnostic.location || "cases.yml";
  const hint = diagnostic.hint ? `\n\nhint:\n  ${diagnostic.hint}` : "";
  return `${diagnostic.path}${line}\n  ${profile}${location}\n  ${diagnostic.message}${hint}`;
}

function formatCasesCompile(result) {
  if (!result.valid) {
    return `cases.yml: invalid\n\n${result.diagnostics.map(formatCaseDiagnostic).join("\n\n")}`;
  }
  const lines = ["cases.yml: ok"];
  for (const profile of result.profiles) {
    lines.push(`profile ${profile.name}: ${profile.caseCount} case(s)`);
  }
  return lines.join("\n");
}

async function compileCasesData({ showSuccess = true } = {}) {
  setStatusCard("cases", "Checking", `${judgeProfile()} cases.yml`);
  const result = await api("/api/cases/compile", {
    method: "POST",
    body: JSON.stringify({
      problem_id: $("problemSelect").value,
      profile: judgeProfile(),
    }),
  });
  if (showSuccess || !result.valid) {
    state.debugLogs = formatCasesCompile(result).split("\n");
    renderDebugLog();
    setBadge(result.valid ? "Cases OK" : "Cases Invalid", result.valid ? "accepted" : "wrong");
    if (result.valid) {
      const profile = result.profiles[0];
      setStatusCard("cases", "OK", `${profile?.caseCount ?? 0} hidden case(s)`);
      setSummary("Hidden cases.yml expanded successfully.", "result-summary success");
    } else {
      const first = result.diagnostics[0];
      setStatusCard("cases", "Invalid", first?.location || "-");
      setSummary(first?.message || "cases.yml compile failed.", "result-summary error");
    }
  } else if (result.valid) {
    const profile = result.profiles[0];
    setStatusCard("cases", "OK", `${profile?.caseCount ?? 0} hidden case(s)`);
  } else {
    const first = result.diagnostics[0];
    state.debugLogs = formatCasesCompile(result).split("\n");
    renderDebugLog();
    setBadge("Cases Invalid", "wrong");
    setStatusCard("cases", "Invalid", first?.location || "-");
    setSummary(first?.message || "cases.yml compile failed.", "result-summary error");
  }
  return result;
}

async function compileCasesOnly() {
  await compileCasesData({ showSuccess: true });
}

function setGenerationProgress(current, total, label = "Data generation") {
  const progress = optional("generationProgress");
  if (!progress) return;
  const safeTotal = Math.max(0, Number(total) || 0);
  const safeCurrent = Math.min(Math.max(0, Number(current) || 0), safeTotal || 0);
  state.generationProgress = { current: safeCurrent, total: safeTotal };
  const percent = safeTotal ? Math.round((safeCurrent / safeTotal) * 100) : 0;
  progress.classList.remove("hidden");
  progress.setAttribute("aria-valuemax", String(safeTotal));
  progress.setAttribute("aria-valuenow", String(safeCurrent));
  setText("generationProgressText", `${safeCurrent} / ${safeTotal}`);
  const fill = optional("generationProgressFill");
  if (fill) fill.style.width = `${percent}%`;
  const labelElement = progress.querySelector(".progress-heading span");
  if (labelElement) labelElement.textContent = label;
}

function hideGenerationProgress() {
  optional("generationProgress")?.classList.add("hidden");
  state.generationProgress = { current: 0, total: 0 };
}

async function generateData() {
  clearDebugLog();
  setBadge("Generating", "neutral");
  setStatusCard("data", "Waiting", judgeProfile());
  setStatusCard("judge", "Idle");
  setStatusCard("run", "-", "No run");
  setSummary("Preparing hidden test data.", "result-summary");
  const compileResult = await compileCasesData({ showSuccess: false });
  if (!compileResult.valid) return;
  const totalCases = compileResult.profiles[0]?.caseCount ?? 0;
  setGenerationProgress(0, totalCases, "Data generation");
  setStatusCard("data", "Generating", `0 / ${totalCases} hidden case(s)`);
  const result = await streamRequest("/api/generate/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      problem_id: $("problemSelect").value,
      profile: judgeProfile(),
      force: $("forceGenerateInput").checked,
    }),
  });
  setGenerationProgress(result.caseCount, result.caseCount, "Data generation");
  setStatusCard("data", "Generated", `${result.caseCount} hidden case(s)`);
  setSummary(`Hidden test data ready: ${result.label}`, "result-summary success");
  setBadge("Generated", "accepted");
}

function appendRunLog(message) {
  state.debugLogs.push(message);
  renderDebugLog();
  updateProgressFromLog(message);
  const output = optional("resultOutput");
  if (output) output.scrollTop = output.scrollHeight;
}

function updateProgressFromLog(message) {
  const generatedCase = message.match(/Validating generated case .+ \((\d+)\/(\d+)\)\./);
  if (message.includes("Compiling cases.yml")) {
    setStatusCard("cases", "Checking", `${judgeProfile()} cases.yml`);
  } else if (message.includes("Preparing generator tools")) {
    setStatusCard("data", "Preparing", judgeProfile());
  } else if (message.includes("Generating input cases")) {
    const total = state.generationProgress.total;
    setGenerationProgress(0, total, "Data generation");
    setStatusCard("data", "Generating", total ? `0 / ${total} hidden case(s)` : judgeProfile());
  } else if (generatedCase) {
    const current = Number(generatedCase[1]);
    const total = Number(generatedCase[2]);
    setGenerationProgress(current, total, "Data generation");
    setStatusCard("data", "Generating", `${current} / ${total} hidden case(s)`);
  } else if (message.includes("Generated data")) {
    const { total } = state.generationProgress;
    if (total) setGenerationProgress(total, total, "Data generation");
    setStatusCard("data", "Generated", judgeProfile());
  } else if (message.includes("Using cached data")) {
    hideGenerationProgress();
    setStatusCard("data", "Ready", judgeProfile());
  } else if (message.includes("Preparing submission file")) {
    setStatusCard("judge", "Preparing", activeSourceName());
  } else if (message.includes("Compiling or preparing user submission")) {
    setStatusCard("judge", "Compiling", activeSourceName());
  } else if (message.includes("Running case")) {
    setStatusCard("judge", "Running", message.replace("Running case ", ""));
  } else if (message.includes("Accepted after")) {
    setStatusCard("judge", "Accepted", message);
  }
}

function runFormData() {
  const formData = new FormData();
  formData.append("problem_id", $("problemSelect").value);
  formData.append("profile", judgeProfile());
  formData.append("source_mode", state.sourceMode);
  if (state.sourceMode === "upload") {
    const file = $("sourceFileInput").files[0];
    if (!file) throw new Error("Source file upload is required.");
    formData.append("file", file);
  } else {
    formData.append("filename", $("filenameInput").value.trim() || $("languageHint").value);
    formData.append("source_text", $("sourceTextInput").value);
  }
  return formData;
}

function parseSseBlock(block) {
  const lines = block.split("\n");
  let event = "message";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  const data = dataLines.length ? JSON.parse(dataLines.join("\n")) : {};
  return { event, data };
}

async function streamRequest(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop();
    for (const block of blocks) {
      if (!block.trim()) continue;
      const { event, data } = parseSseBlock(block);
      if (event === "log") {
        appendRunLog(data.message);
      } else if (event === "result") {
        finalResult = data;
      } else if (event === "error") {
        throw new Error(data.message);
      }
    }
  }
  return finalResult;
}

async function streamRun(formData) {
  return streamRequest("/api/run/stream", {
    method: "POST",
    body: formData,
  });
}

function resultCaseCount(result) {
  if (Number.isFinite(result.caseCount)) return result.caseCount;
  return result.cases?.length || 0;
}

async function restoreRunResult(result) {
  state.artifacts = null;
  $("wrongPanel").classList.add("hidden");
  hideGenerationProgress();
  setBadge(result.status.replaceAll("_", " "), statusClassName(result.status));
  setText("resultMeta", `${result.problemId} · ${result.profile} · ${result.language} · ${result.runId}`);
  setStatusCard("data", "Ready", result.profile);
  setStatusCard(
    "judge",
    result.status.replaceAll("_", " "),
    `${resultCaseCount(result)} hidden case(s)`
  );
  setStatusCard("run", result.runId, runMetricsText(result));
  setSummary(
    runSummary(result),
    result.status === "accepted" ? "result-summary success" : "result-summary error"
  );
  if (result.firstFailedCase) {
    await loadWrongCase(result.runId, result.firstFailedCase);
  }
}

async function runSubmission() {
  state.artifacts = null;
  $("wrongPanel").classList.add("hidden");
  clearDebugLog();
  setBadge("Running", "neutral");
  setStatusCard("data", "Checking", judgeProfile());
  setStatusCard("judge", "Waiting");
  setStatusCard("run", "-", "In progress");
  setSummary("Judging submission with hidden cases.", "result-summary");
  const compileResult = await compileCasesData({ showSuccess: false });
  if (!compileResult.valid) return;
  const totalCases = compileResult.profiles[0]?.caseCount ?? 0;
  setGenerationProgress(0, totalCases, "Data generation");
  const result = await streamRun(runFormData());
  if (!result) throw new Error("Run finished without a result.");
  setBadge(result.status.replaceAll("_", " "), statusClassName(result.status));
  setText("resultMeta", `${result.problemId} · ${result.profile} · ${result.language} · ${result.runId}`);
  setStatusCard("data", "Ready", result.profile);
  setStatusCard(
    "judge",
    result.status.replaceAll("_", " "),
    `${resultCaseCount(result)} hidden case(s)`
  );
  setStatusCard("run", result.runId, runMetricsText(result));
  setSummary(runSummary(result), result.status === "accepted" ? "result-summary success" : "result-summary error");
  if (result.message) state.debugLogs.push(result.message);
  renderDebugLog();
  if (result.firstFailedCase) {
    await loadWrongCase(result.runId, result.firstFailedCase);
  }
  await refreshSecondaryData();
}

function statusClassName(status) {
  if (status === "accepted") return "accepted";
  if (status === "wrong_answer") return "wrong";
  if (status === "compile_error") return "compile";
  if (status === "runtime_error") return "runtime";
  if (status === "time_limit") return "time";
  if (status === "memory_limit") return "memory";
  return "neutral";
}

function runSummary(result) {
  const metrics = runMetricsText(result);
  if (result.status === "accepted") {
    return `Accepted after ${resultCaseCount(result)} hidden case(s). ${metrics}`;
  }
  const failed = result.firstFailedCase ? ` on case ${result.firstFailedCase}` : "";
  return `${result.status.replaceAll("_", " ")}${failed}. ${metrics}`;
}

function runMetricsText(result) {
  const metrics = result.metrics || {};
  const time = metrics.maxTimeLabel || "unavailable";
  const memory = metrics.maxMemoryLabel || "unavailable";
  return `max time ${time} · max memory ${memory}`;
}

async function loadWrongCase(runId, caseId) {
  const artifacts = await api(`/api/runs/${runId}/wrong/${caseId}`);
  state.artifacts = artifacts;
  state.selectedArtifact = "input";
  setText("wrongMeta", `${runId} · case ${caseId}`);
  $("wrongPanel").classList.remove("hidden");
  renderArtifact();
}

function renderArtifact() {
  if (!state.artifacts) return;
  const key = state.selectedArtifact;
  $("artifactOutput").textContent = state.artifacts[key] || "";
  const notice = optional("artifactNotice");
  const truncation = state.artifacts.truncation?.[key];
  if (notice) {
    if (truncation?.truncated) {
      notice.textContent = `긴 데이터라 앞 ${state.artifacts.previewLimit || ARTIFACT_PREVIEW_LIMIT}자만 표시합니다. 생략된 문자: ${truncation.omittedChars}`;
      notice.classList.remove("hidden");
    } else {
      notice.classList.add("hidden");
      notice.textContent = "";
    }
  }
  for (const button of document.querySelectorAll(".artifact-tab")) {
    button.classList.toggle("active", button.dataset.artifact === state.selectedArtifact);
  }
}

async function cacheClear(dryRun, options) {
  if (!dryRun && !confirmCacheClear(options)) {
    $("cacheOutput").textContent = "Cleanup canceled.";
    $("cacheOutput").className = "modal-status muted";
    return;
  }
  $("cacheOutput").textContent = dryRun ? "Calculating cleanup preview..." : "Cleaning cache...";
  $("cacheOutput").className = "modal-status";
  const result = await api("/api/cache/clear", {
    method: "POST",
    body: JSON.stringify({ dry_run: dryRun, ...options }),
  });
  const count = result.targets.length;
  if (dryRun) {
    $("cacheOutput").textContent = formatCacheClearResult(result, `Will delete ${count} target(s)`);
    $("cacheOutput").className = "modal-status";
  } else {
    $("cacheOutput").textContent = formatCacheClearResult(result, `Deleted ${count} target(s)`);
    $("cacheOutput").className = "modal-status success";
    clearSampleCache(options.problem || null);
  }
  await refresh();
}

function confirmCacheClear(options) {
  const target = options.all_entries ? "all cache entries" : "run artifacts";
  return window.confirm(`Delete ${target}? This cannot be undone.`);
}

function formatCacheClearResult(result, heading) {
  const targets = result.targets || [];
  if (!targets.length) return `${heading}, ${result.totalSizeLabel}\nNo matching cache targets.`;
  const visibleTargets = targets.slice(0, 8).map((target) => {
    const label = target.label === "." ? "entire cache root" : target.label;
    return `- ${label}`;
  });
  const omitted = targets.length > visibleTargets.length ? `\n- ...and ${targets.length - visibleTargets.length} more` : "";
  return `${heading}, ${result.totalSizeLabel}\n${visibleTargets.join("\n")}${omitted}`;
}

async function withErrors(action) {
  setBusy(true);
  try {
    await action();
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

function showError(message) {
  const packModal = optional("packModal");
  const cacheModal = optional("cacheModal");
  const packOpen = packModal && !packModal.classList.contains("hidden");
  const cacheOpen = cacheModal && !cacheModal.classList.contains("hidden");
  if (packModal && !packModal.classList.contains("hidden")) {
    $("packStatus").textContent = message;
    $("packStatus").className = "modal-status error";
  }
  if (cacheModal && !cacheModal.classList.contains("hidden")) {
    $("cacheOutput").textContent = message;
    $("cacheOutput").className = "modal-status error";
  }
  if (packOpen || cacheOpen) {
    showToast(message, "error");
    return;
  }
  setBadge("Error", "wrong");
  setSummary(message, "result-summary error");
  state.debugLogs.push(`Error: ${message}`);
  renderDebugLog();
}

function openModal(id) {
  optional("modalBackdrop")?.classList.remove("hidden");
  optional(id)?.classList.remove("hidden");
  if (id === "cacheModal") {
    renderCacheModalSummary(state.cache);
  }
}

function closeModals() {
  optional("modalBackdrop")?.classList.add("hidden");
  optional("packModal")?.classList.add("hidden");
  optional("cacheModal")?.classList.add("hidden");
}

function setMode(mode) {
  state.sourceMode = mode;
  $("uploadModeButton").classList.toggle("active", mode === "upload");
  $("textModeButton").classList.toggle("active", mode === "text");
  $("uploadModeButton").setAttribute("aria-selected", String(mode === "upload"));
  $("textModeButton").setAttribute("aria-selected", String(mode === "text"));
  $("uploadSourcePanel").classList.toggle("hidden", mode !== "upload");
  $("textSourcePanel").classList.toggle("hidden", mode !== "text");
  updateLanguageBadge();
}

function updatePackActionState() {
  const fileInput = optional("packFileInput");
  setDisabled("uploadPackButton", state.isBusy || !fileInput?.files?.length);
  setDisabled("downloadPackButton", state.isBusy);
}

function bindDropZone() {
  const zone = $("uploadSourcePanel");
  const input = $("sourceFileInput");
  for (const eventName of ["dragenter", "dragover"]) {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.add("drag-over");
    });
  }
  for (const eventName of ["dragleave", "drop"]) {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.remove("drag-over");
    });
  }
  zone.addEventListener("drop", (event) => {
    const files = event.dataTransfer?.files;
    if (files?.length) {
      input.files = files;
      setMode("upload");
      updateLanguageBadge();
    }
  });
}

function bindEvents() {
  applyTheme(preferredTheme());
  on("themeToggleButton", "click", toggleTheme);
  on("addProblemButton", "click", () => openModal("packModal"));
  on("cacheManageButton", "click", () => openModal("cacheModal"));
  on("refreshButton", "click", () => withErrors(refresh));
  on("modalBackdrop", "click", closeModals);
  for (const button of document.querySelectorAll("[data-modal-close]")) {
    button.addEventListener("click", closeModals);
  }
  on("debugModeInput", "change", renderDebugLog);
  on("problemSelect", "change", () => withErrors(handleProblemChange));
  on("sourceFileInput", "change", updateLanguageBadge);
  on("filenameInput", "input", updateLanguageBadge);
  on("languageHint", "change", () => {
    syncFilenamePlaceholder();
    if (!$("filenameInput").value.trim()) updateLanguageBadge();
  });
  on("sourceTextInput", "input", () => {
    updateEditorView();
    updateActionState();
  });
  on("sourceTextInput", "scroll", syncEditorScroll);
  const sourceTextInput = optional("sourceTextInput");
  if (sourceTextInput) {
    sourceTextInput.addEventListener("keydown", (event) => {
      if (event.key === "Tab") {
        event.preventDefault();
        insertEditorText("  ");
      }
    });
  }
  on("uploadModeButton", "click", () => setMode("upload"));
  on("textModeButton", "click", () => setMode("text"));
  on("uploadPackButton", "click", () => withErrors(uploadPack));
  on("downloadPackButton", "click", () => withErrors(downloadOfficialPack));
  on("packFileInput", "change", updatePackActionState);
  on("casesCompileButton", "click", () => withErrors(compileCasesOnly));
  on("generateButton", "click", () => withErrors(generateData));
  on("runButton", "click", () => withErrors(runSubmission));
  on("cachePreviewButton", "click", () => withErrors(() => cacheClear(true, { all_entries: true })));
  on("cacheClearRunsButton", "click", () => withErrors(() => cacheClear(false, { runs: true })));
  on("cacheClearAllButton", "click", () => withErrors(() => cacheClear(false, { all_entries: true })));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModals();
  });
  for (const button of document.querySelectorAll(".artifact-tab")) {
    button.addEventListener("click", () => {
      state.selectedArtifact = button.dataset.artifact;
      renderArtifact();
    });
  }
  bindDropZone();
  syncFilenamePlaceholder();
  updateEditorView();
  updateActionState();
  updatePackActionState();
}

bindEvents();
withErrors(refresh);
