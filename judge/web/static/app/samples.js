/**
 * 샘플 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;
/**
 * 샘플 캐시 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 *
 * @param {string} problemId 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
 */
function clearSampleCache(problemId = null) {
  if (problemId) {
    delete state.sampleCache[problemId];
    return;
  }
  state.sampleCache = {};
}
/**
 * 샘플 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {object} data 파일, API 응답, UI 렌더링에 사용할 구조화된 데이터입니다.
 */
function renderSamples(data) {
  const container = app.optional("sampleCases");
  if (!container) return;
  container.innerHTML = "";
  container.removeAttribute("aria-busy");
  if (!data) {
    app.setText("sampleMeta", "선택된 문제가 없습니다.");
    container.textContent = "불러온 예제 케이스가 없습니다.";
    container.classList.add("muted");
    return;
  }
  const source = data.cached ? "캐시" : "생성됨";
  app.setText(
    "sampleMeta",
    `${data.caseCount}개 ${data.profile || app.sampleProfile()} 케이스 · ${source} · ${data.label}`
  );
  if (!data.cases?.length) {
    container.textContent = "선언된 예제 케이스가 없습니다.";
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
/**
 * 샘플 loading 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {string} problemId 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
 */
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
/**
 * 샘플을 파일이나 캐시에서 읽고 필요한 기본값을 적용합니다.
 *
 * @param {object} options 호출자가 동작 일부를 조정하기 위해 넘기는 선택 옵션 묶음입니다.
 */
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
