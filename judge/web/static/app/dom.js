const app = window.AljApp;

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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function on(id, eventName, handler) {
  const element = optional(id);
  if (element) element.addEventListener(eventName, handler);
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

Object.assign(app, {
  $,
  escapeHtml,
  on,
  optional,
  setDisabled,
  setText,
  showToast,
});
