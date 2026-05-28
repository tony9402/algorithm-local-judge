const app = window.AljApp;

/**
 * optional 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
const optional = (id) => document.getElementById(id);
/**
 * $ 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
const $ = (id) => {
  const element = optional(id);
  if (!element) throw new Error(`Missing UI element: ${id}`);
  return element;
};

/**
 * setText 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function setText(id, value) {
  const element = optional(id);
  if (element) element.textContent = value;
}

/**
 * setDisabled 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @param {any} isDisabled `isDisabled` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function setDisabled(id, isDisabled) {
  const element = optional(id);
  if (element) element.disabled = isDisabled;
}

/**
 * escapeHtml 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/**
 * on 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @param {any} eventName `eventName` 값입니다.
 * @param {any} handler `handler` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function on(id, eventName, handler) {
  const element = optional(id);
  if (element) element.addEventListener(eventName, handler);
}

/**
 * showToast 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @param {any} className `className` 값입니다.
 * @param {any} timeoutMs `timeoutMs` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

Object.assign(app, {
  $,
  escapeHtml,
  on,
  optional,
  setDisabled,
  setText,
  showToast,
});
