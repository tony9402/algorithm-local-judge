/**
 * optional 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export const optional = (id) => document.getElementById(id);

/**
 * $ 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export const $ = (id) => {
  const element = optional(id);
  if (!element) throw new Error(`Missing UI element: ${id}`);
  return element;
};

/**
 * resetWorkspaceScroll 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function resetWorkspaceScroll() {
  document.querySelector(".workspace")?.scrollTo({ top: 0, left: 0 });
  window.scrollTo({ top: 0, left: 0 });
}

/**
 * setText 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function setText(id, value) {
  const element = optional(id);
  if (element) element.textContent = value;
}

/**
 * escapeHtml 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
