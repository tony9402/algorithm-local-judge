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

function languageIdFromName(name) {
  const lowered = (name || "").toLowerCase();
  if (lowered.endsWith(".cpp") || lowered.endsWith(".cc") || lowered.endsWith(".cxx")) return "cpp";
  if (lowered.endsWith(".py")) return "python";
  if (lowered.endsWith(".java")) return "java";
  return "";
}

function languageNameFromId(languageId) {
  return { cpp: "C++", python: "Python", pypy: "PyPy", java: "Java" }[languageId] || "Unknown";
}

function extensionForLanguage(languageId) {
  return { cpp: ".cpp", python: ".py", pypy: ".py", java: ".java" }[languageId] || "";
}

function explicitLanguageForName(detected, hintValue) {
  if (detected === "python" && hintValue === "pypy") return "pypy";
  return detected || hintValue || "python";
}

function normalizedSourceName() {
  const input = app.optional("filenameInput");
  const hint = app.optional("languageHint");
  const filename = input?.value.trim() || "";
  const detected = languageIdFromName(filename);
  const languageId = explicitLanguageForName(detected, hint?.value);
  if (!filename) return languageId === "java" ? "Main.java" : `main${extensionForLanguage(languageId)}`;
  if (detected || /\.[^/.]+$/.test(filename)) return filename;
  return `${filename}${extensionForLanguage(languageId)}`;
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
  return sourceTextReady();
}
function activeSourceName() {
  return normalizedSourceName();
}
function sourceReadinessText() {
  if (!hasSelectedProblem()) return "문제를 먼저 설치하세요";
  if (!hasRunnableSource()) {
    return "코드 입력이 필요합니다";
  }
  return `${activeSourceName()} 준비됨`;
}
/**
 * action state 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updateActionState() {
  const hasProblem = hasSelectedProblem();
  const hasSource = hasRunnableSource();
  app.setDisabled("casesCompileButton", state.isBusy || !hasProblem);
  app.setDisabled("generateButton", state.isBusy || !hasProblem);
  const cooldown = app.submissionCooldownRemaining?.() || 0;
  const blocked = state.isBusy || !hasProblem || !hasSource || cooldown > 0;
  app.setDisabled("runButton", blocked);
  app.setDisabled("sampleRunButton", blocked || !app.problemSupportsProfile?.("sample"));
  app.setDisabled("fullRunButton", blocked);

  const readiness = app.optional("sourceReadiness");
  if (readiness) {
    readiness.textContent = cooldown > 0 ? `${cooldown}초 후 다시 제출할 수 있습니다` : sourceReadinessText();
    readiness.classList.toggle("ready", hasProblem && hasSource);
  }
}

function syncFilenamePlaceholder() {
  const input = app.optional("filenameInput");
  const hint = app.optional("languageHint");
  if (input && hint) {
    input.placeholder = hint.value === "java" ? "Main" : "main";
  }
}
/**
 * language badge 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updateLanguageBadge() {
  const filename = app.$("filenameInput").value || "";
  const detected = languageIdFromName(filename);
  const hint = app.optional("languageHint");
  if (detected && hint && !(detected === "python" && hint.value === "pypy")) hint.value = detected;
  const languageId = explicitLanguageForName(detected, hint?.value || "");
  const language = languageId ? languageNameFromId(languageId) : "No source";
  const name = normalizedSourceName();
  app.setText("languageBadge", language);
  app.setText("editorFileLabel", name || "main.py");
  app.setText("editorLanguageLabel", language);
  app.updateCodeHighlight();
  updateActionState();
}

Object.assign(app, {
  activeSourceName,
  extensionForLanguage,
  hasRunnableSource,
  hasSelectedProblem,
  languageIdFromName,
  languageFromName,
  languageNameFromId,
  normalizedSourceName,
  sourceReadinessText,
  sourceTextReady,
  sourceUploadReady,
  syncFilenamePlaceholder,
  updateActionState,
  updateLanguageBadge,
});
