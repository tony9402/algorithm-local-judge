/**
 * 소스 readiness 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;

function languageFromName(name) {
  const lowered = (name || "").toLowerCase();
  if (lowered.endsWith(".cpp") || lowered.endsWith(".cc") || lowered.endsWith(".cxx")) return "C++";
  if (lowered.endsWith(".py")) return "Python";
  if (lowered.endsWith(".java")) return "Java";
  return "Unknown";
}

function sourceTextReady() {
  const input = app.optional("sourceTextInput");
  return Boolean(input?.value.trim());
}

function sourceUploadReady() {
  return Boolean(app.optional("sourceFileInput")?.files[0]);
}
function hasSelectedProblem() {
  return Boolean(state.selectedProblem || app.optional("problemSelect")?.value);
}
function hasRunnableSource() {
  return state.sourceMode === "upload" ? sourceUploadReady() : sourceTextReady();
}
function activeSourceName() {
  if (state.sourceMode === "upload") return app.$("sourceFileInput").files[0]?.name || "source";
  return app.$("filenameInput").value.trim() || app.$("languageHint").value || "source";
}
function sourceReadinessText() {
  if (!hasSelectedProblem()) return "Install a problem first";
  if (!hasRunnableSource()) {
    return state.sourceMode === "upload" ? "Source file needed" : "Source code needed";
  }
  return `${activeSourceName()} ready`;
}
/**
 * action state 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updateActionState() {
  const hasProblem = hasSelectedProblem();
  const hasSource = hasRunnableSource();
  app.setDisabled("casesCompileButton", state.isBusy || !hasProblem);
  app.setDisabled("generateButton", state.isBusy || !hasProblem);
  app.setDisabled("runButton", state.isBusy || !hasProblem || !hasSource);

  const readiness = app.optional("sourceReadiness");
  if (readiness) {
    readiness.textContent = sourceReadinessText();
    readiness.classList.toggle("ready", hasProblem && hasSource);
  }
}

function syncFilenamePlaceholder() {
  const input = app.optional("filenameInput");
  const hint = app.optional("languageHint");
  if (input && hint) input.placeholder = hint.value || "main.cpp";
}
/**
 * language badge 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updateLanguageBadge() {
  const name =
    state.sourceMode === "upload"
      ? app.$("sourceFileInput").files[0]?.name || ""
      : app.$("filenameInput").value || app.$("languageHint").value;
  const language = name ? languageFromName(name) : "No source";
  app.setText("languageBadge", language);
  app.setText("editorFileLabel", name || "main.py");
  app.setText("editorLanguageLabel", language);
  app.updateCodeHighlight();
  updateActionState();
}

Object.assign(app, {
  activeSourceName,
  hasRunnableSource,
  hasSelectedProblem,
  languageFromName,
  sourceReadinessText,
  sourceTextReady,
  sourceUploadReady,
  syncFilenamePlaceholder,
  updateActionState,
  updateLanguageBadge,
});
