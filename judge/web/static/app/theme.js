const app = window.AljApp;

function preferredTheme() {
  const saved = localStorage.getItem("alj-theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("alj-theme", theme);
  const button = app.optional("themeToggleButton");
  if (button) {
    button.textContent = theme === "dark" ? "Light" : "Dark";
    button.setAttribute("aria-pressed", String(theme === "dark"));
  }
}

function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}

Object.assign(app, {
  applyTheme,
  preferredTheme,
  toggleTheme,
});
