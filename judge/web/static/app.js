const state = {
  problems: [],
  selectedProblem: null,
  sourceMode: "upload",
  artifacts: null,
  selectedArtifact: "input",
  cache: null,
  debugLogs: [],
  sampleLoadToken: 0,
  sampleCache: {},
  config: {
    sampleProfile: "sample",
    judgeProfile: "hidden",
    webDebug: false,
  },
};

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
  setDisabled("addProblemButton", isBusy);
  setDisabled("cacheManageButton", isBusy);
  setDisabled("casesCompileButton", isBusy);
  setDisabled("generateButton", isBusy);
  setDisabled("runButton", isBusy);
  setDisabled("uploadPackButton", isBusy);
  setDisabled("downloadPackButton", isBusy);
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

function updateLanguageBadge() {
  const name =
    state.sourceMode === "upload"
      ? $("sourceFileInput").files[0]?.name
      : $("filenameInput").value || $("languageHint").value;
  setText("languageBadge", languageFromName(name));
}

function renderProblems(problems) {
  state.problems = problems;
  const list = $("problemList");
  const select = $("problemSelect");
  list.innerHTML = "";
  select.innerHTML = "";
  if (!problems.length) {
    state.selectedProblem = null;
    list.textContent = "No problems installed.";
    list.classList.add("muted");
    renderSamples(null);
    return;
  }
  list.classList.remove("muted");
  for (const problem of problems) {
    const item = document.createElement("button");
    item.className = "list-item";
    item.type = "button";
    item.dataset.problemId = problem.problemId;
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
  $("cacheSummary").innerHTML = `
    <div>Total ${cache.totalSizeLabel}</div>
    <div>Problem caches ${cache.problems.length}</div>
    <div>Runs ${cache.runs.count}</div>
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
  `;
}

function renderProblemSelection() {
  const problemId = state.selectedProblem;
  for (const item of $("problemList").querySelectorAll(".list-item")) {
    item.classList.toggle("active", item.dataset.problemId === problemId);
  }
}

async function handleProblemChange() {
  const problemId = $("problemSelect").value;
  state.selectedProblem = problemId;
  renderProblemSelection();
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
    const [packs, cache] = await Promise.all([api("/api/packs"), api("/api/cache")]);
    renderPacks(packs);
    renderCache(cache);
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

async function generateData() {
  clearDebugLog();
  setBadge("Generating", "neutral");
  setStatusCard("data", "Waiting", judgeProfile());
  setStatusCard("judge", "Idle");
  setStatusCard("run", "-", "No run");
  setSummary("Preparing hidden test data.", "result-summary");
  const compileResult = await compileCasesData({ showSuccess: false });
  if (!compileResult.valid) return;
  setStatusCard("data", "Generating", judgeProfile());
  const result = await streamRequest("/api/generate/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      problem_id: $("problemSelect").value,
      profile: judgeProfile(),
      force: $("forceGenerateInput").checked,
    }),
  });
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
  if (message.includes("Compiling cases.yml")) {
    setStatusCard("cases", "Checking", `${judgeProfile()} cases.yml`);
  } else if (message.includes("Preparing generator tools")) {
    setStatusCard("data", "Preparing", judgeProfile());
  } else if (message.includes("Generating input cases")) {
    setStatusCard("data", "Generating", judgeProfile());
  } else if (message.includes("Generated data")) {
    setStatusCard("data", "Generated", judgeProfile());
  } else if (message.includes("Preparing submission file")) {
    setStatusCard("judge", "Preparing", $("sourceFileInput").files[0]?.name || "source");
  } else if (message.includes("Compiling or preparing user submission")) {
    setStatusCard("judge", "Compiling", $("sourceFileInput").files[0]?.name || "source");
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
  const result = await streamRun(runFormData());
  if (!result) throw new Error("Run finished without a result.");
  setBadge(result.status.replaceAll("_", " "), statusClassName(result.status));
  setText("resultMeta", `${result.problemId} · ${result.profile} · ${result.language} · ${result.runId}`);
  setStatusCard("data", "Ready", result.profile);
  setStatusCard(
    "judge",
    result.status.replaceAll("_", " "),
    `${result.cases.length} hidden case(s)`
  );
  setStatusCard("run", result.runId, runMetricsText(result));
  setSummary(runSummary(result), result.status === "accepted" ? "result-summary success" : "result-summary error");
  if (result.message) state.debugLogs.push(result.message);
  renderDebugLog();
  if (result.firstFailedCase) {
    await loadWrongCase(result.runId, result.firstFailedCase);
  }
}

function statusClassName(status) {
  if (status === "accepted") return "accepted";
  if (status === "wrong_answer") return "wrong";
  if (status === "compile_error") return "compile";
  if (status === "runtime_error") return "runtime";
  if (status === "time_limit") return "time";
  return "neutral";
}

function runSummary(result) {
  const metrics = runMetricsText(result);
  if (result.status === "accepted") {
    return `Accepted after ${result.cases.length} hidden case(s). ${metrics}`;
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
  $("artifactOutput").textContent = state.artifacts[state.selectedArtifact] || "";
  for (const button of document.querySelectorAll(".artifact-tab")) {
    button.classList.toggle("active", button.dataset.artifact === state.selectedArtifact);
  }
}

async function cacheClear(dryRun, options) {
  $("cacheOutput").textContent = dryRun ? "Calculating cleanup preview..." : "Cleaning cache...";
  $("cacheOutput").className = "modal-status";
  const result = await api("/api/cache/clear", {
    method: "POST",
    body: JSON.stringify({ dry_run: dryRun, ...options }),
  });
  const count = result.targets.length;
  if (dryRun) {
    $("cacheOutput").textContent = `${count} target(s), ${result.totalSizeLabel}`;
    $("cacheOutput").className = "modal-status";
  } else {
    $("cacheOutput").textContent = `Deleted ${count} target(s), ${result.totalSizeLabel}`;
    $("cacheOutput").className = "modal-status success";
    clearSampleCache(options.problem || null);
  }
  await refresh();
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
  setBadge("Error", "wrong");
  setSummary(message, "result-summary error");
  state.debugLogs.push(`Error: ${message}`);
  renderDebugLog();
  const packModal = optional("packModal");
  const cacheModal = optional("cacheModal");
  if (packModal && !packModal.classList.contains("hidden")) {
    $("packStatus").textContent = message;
    $("packStatus").className = "modal-status error";
  }
  if (cacheModal && !cacheModal.classList.contains("hidden")) {
    $("cacheOutput").textContent = message;
    $("cacheOutput").className = "modal-status error";
  }
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
  $("uploadSourcePanel").classList.toggle("hidden", mode !== "upload");
  $("textSourcePanel").classList.toggle("hidden", mode !== "text");
  updateLanguageBadge();
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
    if (!$("filenameInput").value.trim()) updateLanguageBadge();
  });
  on("uploadModeButton", "click", () => setMode("upload"));
  on("textModeButton", "click", () => setMode("text"));
  on("uploadPackButton", "click", () => withErrors(uploadPack));
  on("downloadPackButton", "click", () => withErrors(downloadOfficialPack));
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
}

bindEvents();
withErrors(refresh);
