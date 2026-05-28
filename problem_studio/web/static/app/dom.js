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
