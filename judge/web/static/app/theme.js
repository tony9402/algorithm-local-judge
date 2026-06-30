/**
 * theme 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

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
    button.textContent = theme === "dark" ? "다크 모드" : "라이트 모드";
    button.setAttribute("aria-pressed", String(theme === "dark"));
    button.setAttribute(
      "aria-label",
      theme === "dark" ? "현재 다크 모드, 라이트 모드로 전환" : "현재 라이트 모드, 다크 모드로 전환"
    );
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
