/**
 * 캐시 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { escapeHtml, state } = app;
/**
 * 캐시 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {any} cache 캐시을 계산하거나 검증할 때 필요한 캐시 입력입니다.
 */
function renderCache(cache) {
  state.cache = cache;
  const sources = cache.sources || { count: 0 };
  app.$("cacheSummary").innerHTML = `
    <div>Total ${escapeHtml(cache.totalSizeLabel)}</div>
    <div>Problem caches ${escapeHtml(cache.problems.length)}</div>
    <div>Runs ${escapeHtml(cache.runs.count)}</div>
    <div>Sources ${escapeHtml(sources.count)}</div>
  `;
  renderCacheModalSummary(cache);
}
/**
 * 캐시 모달 summary 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {any} cache 캐시 모달 summary을 계산하거나 검증할 때 필요한 캐시 입력입니다.
 */
function renderCacheModalSummary(cache) {
  const summary = app.optional("cacheModalSummary");
  if (!cache || !summary) return;
  const sources = cache.sources || { count: 0, sizeLabel: "0 B" };
  summary.innerHTML = `
    <div class="status-card">
      <span>Total</span>
      <strong>${escapeHtml(cache.totalSizeLabel)}</strong>
      <small>Cache size</small>
    </div>
    <div class="status-card">
      <span>Problem Data</span>
      <strong>${escapeHtml(cache.problems.length)}</strong>
      <small>Generated caches</small>
    </div>
    <div class="status-card">
      <span>Runs</span>
      <strong>${escapeHtml(cache.runs.count)}</strong>
      <small>${escapeHtml(cache.runs.sizeLabel || "0 B")}</small>
    </div>
    <div class="status-card">
      <span>Sources</span>
      <strong>${escapeHtml(sources.count)}</strong>
      <small>${escapeHtml(sources.sizeLabel || "0 B")}</small>
    </div>
  `;
}
async function cacheClear(dryRun, options) {
  if (!dryRun && !confirmCacheClear(options)) {
    app.$("cacheOutput").textContent = "Cleanup canceled.";
    app.$("cacheOutput").className = "modal-status muted";
    return;
  }
  app.$("cacheOutput").textContent = dryRun ? "Calculating cleanup preview..." : "Cleaning cache...";
  app.$("cacheOutput").className = "modal-status";
  const result = await app.api("/api/cache/clear", {
    method: "POST",
    body: JSON.stringify({ dry_run: dryRun, ...options }),
  });
  const count = result.targets.length;
  if (dryRun) {
    app.$("cacheOutput").textContent = formatCacheClearResult(result, `Will delete ${count} target(s)`);
    app.$("cacheOutput").className = "modal-status";
  } else {
    app.$("cacheOutput").textContent = formatCacheClearResult(result, `Deleted ${count} target(s)`);
    app.$("cacheOutput").className = "modal-status success";
    app.clearSampleCache(options.problem || null);
  }
  await app.refresh();
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

Object.assign(app, {
  cacheClear,
  confirmCacheClear,
  formatCacheClearResult,
  renderCache,
  renderCacheModalSummary,
});
