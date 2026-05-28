const app = window.AljApp;

/**
 * preferredTheme 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function preferredTheme() {
  const saved = localStorage.getItem("alj-theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * applyTheme 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} theme `theme` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("alj-theme", theme);
  const button = app.optional("themeToggleButton");
  if (button) {
    button.textContent = theme === "dark" ? "Light" : "Dark";
    button.setAttribute("aria-pressed", String(theme === "dark"));
  }
}

/**
 * toggleTheme 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}

Object.assign(app, {
  applyTheme,
  preferredTheme,
  toggleTheme,
});
