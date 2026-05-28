const app = window.AljApp;
const { state } = app;

/**
 * languageFromName 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} name 이름입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function languageFromName(name) {
  /**
   * lowered 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} name 이름입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  const lowered = (name || "").toLowerCase();
  if (lowered.endsWith(".cpp") || lowered.endsWith(".cc") || lowered.endsWith(".cxx")) return "C++";
  if (lowered.endsWith(".py")) return "Python";
  if (lowered.endsWith(".java")) return "Java";
  return "Unknown";
}

/**
 * sourceTextReady 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function sourceTextReady() {
  const input = app.optional("sourceTextInput");
  return Boolean(input?.value.trim());
}

/**
 * sourceUploadReady 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function sourceUploadReady() {
  return Boolean(app.optional("sourceFileInput")?.files[0]);
}

/**
 * hasSelectedProblem 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function hasSelectedProblem() {
  return Boolean(state.selectedProblem || app.optional("problemSelect")?.value);
}

/**
 * hasRunnableSource 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function hasRunnableSource() {
  return state.sourceMode === "upload" ? sourceUploadReady() : sourceTextReady();
}

/**
 * activeSourceName 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function activeSourceName() {
  if (state.sourceMode === "upload") return app.$("sourceFileInput").files[0]?.name || "source";
  return app.$("filenameInput").value.trim() || app.$("languageHint").value || "source";
}

/**
 * sourceReadinessText 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function sourceReadinessText() {
  if (!hasSelectedProblem()) return "Install a problem first";
  if (!hasRunnableSource()) {
    return state.sourceMode === "upload" ? "Source file needed" : "Source code needed";
  }
  return `${activeSourceName()} ready`;
}

/**
 * updateActionState 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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

/**
 * syncFilenamePlaceholder 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function syncFilenamePlaceholder() {
  const input = app.optional("filenameInput");
  const hint = app.optional("languageHint");
  if (input && hint) input.placeholder = hint.value || "main.cpp";
}

/**
 * updateLanguageBadge 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
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
