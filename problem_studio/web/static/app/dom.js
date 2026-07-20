/**
 * dom 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */
export const optional = (id) => document.getElementById(id);
export const $ = (id) => {
  const element = optional(id);
  if (!element) throw new Error(`Missing UI element: ${id}`);
  return element;
};
export function resetWorkspaceScroll() {
  document.querySelector(".workspace")?.scrollTo({ top: 0, left: 0 });
  window.scrollTo({ top: 0, left: 0 });
}
/**
 * 텍스트 값을 내부 상태나 DOM 요소에 반영합니다.
 *
 * @param {any} id 텍스트을 계산하거나 검증할 때 필요한 ID 입력입니다.
 * @param {any} value 검증하거나 상태에 반영할 입력 값입니다.
 */
export function setText(id, value) {
  const element = optional(id);
  if (element) element.textContent = value;
}
export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function compactPath(value) {
  const original = String(value || "");
  if (!original) return "";
  const normalized = original.replaceAll("\\", "/").replace(/^file:\/\//, "");
  const home = normalized.match(/^\/(?:Users|home)\/[^/]+(\/.*)?$/);
  if (home) {
    const relative = home[1] || "";
    const parts = relative.split("/").filter(Boolean);
    return parts.length <= 3 ? `~${relative}` : `~/…/${parts.slice(-2).join("/")}`;
  }
  const windowsHome = normalized.match(/^[A-Za-z]:\/Users\/[^/]+(\/.*)?$/i);
  if (windowsHome) {
    const parts = (windowsHome[1] || "").split("/").filter(Boolean);
    return parts.length <= 3 ? `~/${parts.join("/")}` : `~/…/${parts.slice(-2).join("/")}`;
  }
  const absolute = normalized.startsWith("/") || /^[A-Za-z]:\//.test(normalized);
  if (!absolute) return original;
  const parts = normalized.split("/").filter(Boolean);
  return parts.length <= 2 ? normalized : `…/${parts.slice(-2).join("/")}`;
}

export function pathDisclosureHtml(value) {
  const full = String(value || "");
  const compact = compactPath(full);
  if (!full || compact === full) return escapeHtml(full);
  return `
    <details class="path-disclosure">
      <summary title="${escapeHtml(full)}">${escapeHtml(compact)}</summary>
      <code>${escapeHtml(full)}</code>
    </details>
  `;
}
