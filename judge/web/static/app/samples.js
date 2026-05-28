const app = window.AljApp;
const { state } = app;

function clearSampleCache(problemId = null) {
  if (problemId) {
    delete state.sampleCache[problemId];
    return;
  }
  state.sampleCache = {};
}

function renderSamples(data) {
  const container = app.optional("sampleCases");
  if (!container) return;
  container.innerHTML = "";
  container.removeAttribute("aria-busy");
  if (!data) {
    app.setText("sampleMeta", "No problem selected.");
    container.textContent = "No sample cases loaded.";
    container.classList.add("muted");
    return;
  }
  const source = data.cached ? "cache" : "generated";
  app.setText(
    "sampleMeta",
    `${data.caseCount} ${data.profile || app.sampleProfile()} case(s) · ${source} · ${data.label}`
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
  const container = app.optional("sampleCases");
  if (!container) return;
  app.setText("sampleMeta", `${problemId} sample 데이터를 준비하는 중...`);
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
  const response = await app.apiResponse(
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

Object.assign(app, {
  clearSampleCache,
  loadSamples,
  renderSampleLoading,
  renderSamples,
});
