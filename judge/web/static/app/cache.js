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
    <div>전체 ${escapeHtml(cache.totalSizeLabel)}</div>
    <div>문제 데이터 ${escapeHtml(cache.problems.length)}</div>
    <div>채점 기록 ${escapeHtml(cache.runs.count)}</div>
    <div>소스 ${escapeHtml(sources.count)}</div>
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
      <span>전체</span>
      <strong>${escapeHtml(cache.totalSizeLabel)}</strong>
      <small>캐시 크기</small>
    </div>
    <div class="status-card">
      <span>문제 데이터</span>
      <strong>${escapeHtml(cache.problems.length)}</strong>
      <small>생성된 데이터 캐시</small>
    </div>
    <div class="status-card">
      <span>채점 기록</span>
      <strong>${escapeHtml(cache.runs.count)}</strong>
      <small>${escapeHtml(cache.runs.sizeLabel || "0 B")}</small>
    </div>
    <div class="status-card">
      <span>소스</span>
      <strong>${escapeHtml(sources.count)}</strong>
      <small>${escapeHtml(sources.sizeLabel || "0 B")}</small>
    </div>
  `;
}
async function cacheClear(dryRun, options) {
  if (!dryRun && !confirmCacheClear(options)) {
    app.$("cacheOutput").textContent = "정리를 취소했습니다.";
    app.$("cacheOutput").className = "modal-status muted";
    return;
  }
  app.$("cacheOutput").textContent = dryRun ? "삭제 미리보기를 계산하는 중..." : "캐시를 정리하는 중...";
  app.$("cacheOutput").className = "modal-status";
  const result = await app.api("/api/cache/clear", {
    method: "POST",
    body: JSON.stringify({ dry_run: dryRun, ...options }),
  });
  const count = result.targets.length;
  if (dryRun) {
    app.$("cacheOutput").textContent = formatCacheClearResult(result, `${count}개 대상을 삭제할 예정`);
    app.$("cacheOutput").className = "modal-status";
  } else {
    app.$("cacheOutput").textContent = formatCacheClearResult(result, `${count}개 대상을 삭제했습니다`);
    app.$("cacheOutput").className = "modal-status success";
    app.clearSampleCache(options.problem || null);
  }
  await app.refresh();
}

function confirmCacheClear(options) {
  const target = options.all_entries ? "모든 캐시 항목" : "채점 산출물";
  return window.confirm(`${target}을 삭제합니다.\n삭제 후에는 되돌릴 수 없습니다.`);
}

function formatCacheClearResult(result, heading) {
  const targets = result.targets || [];
  if (!targets.length) return `${heading}, ${result.totalSizeLabel}\n일치하는 삭제 대상이 없습니다.`;
  const visibleTargets = targets.slice(0, 8).map((target) => {
    const label = target.label === "." ? "전체 캐시 루트" : target.label;
    return `- ${label}`;
  });
  const omitted = targets.length > visibleTargets.length ? `\n- 외 ${targets.length - visibleTargets.length}개` : "";
  return `${heading}, ${result.totalSizeLabel}\n${visibleTargets.join("\n")}${omitted}`;
}

Object.assign(app, {
  cacheClear,
  confirmCacheClear,
  formatCacheClearResult,
  renderCache,
  renderCacheModalSummary,
});
