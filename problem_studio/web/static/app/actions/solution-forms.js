import { $, setText } from "../dom.js";
import { updateModalEditorOptions } from "../editor/codemirror.js";
import { EXTENSIONS, SAFE_SOLUTION_NAME } from "../state.js";

function formatSolutionFilename(name, expected, language) {
  const normalizedName = name.trim().replaceAll(" ", "_") || "solution";
  return `${normalizedName}.${expected}${EXTENSIONS[language] || ".cpp"}`;
}

function solutionNameError(value) {
  const name = value.trim().replaceAll(" ", "_");
  if (!name) return "솔루션 이름을 입력하세요.";
  if (!SAFE_SOLUTION_NAME.test(name)) return "영문, 숫자, _, -, . 만 사용할 수 있습니다.";
  return "";
}

function updateSolutionFormValidity(config) {
  const name = $(config.nameId).value;
  const error = solutionNameError(name);
  const expected = $(config.expectedId).value;
  const language = $(config.languageId).value;
  setText(config.previewId, formatSolutionFilename(name, expected, language));
  setText(config.errorId, error);
  $(config.buttonId).disabled = Boolean(error);
  $(config.previewId).classList.toggle("invalid", Boolean(error));
  return !error;
}

export function updateSolutionPreview() {
  const valid = updateSolutionFormValidity({
    nameId: "solutionCreateName",
    expectedId: "solutionCreateExpected",
    languageId: "solutionCreateLanguage",
    previewId: "solutionCreatePreview",
    errorId: "solutionCreateNameError",
    buttonId: "solutionCreateButton",
  });
  updateModalEditorOptions();
  return valid;
}

export function updateSolutionRenamePreview() {
  const valid = updateSolutionFormValidity({
    nameId: "solutionName",
    expectedId: "solutionExpected",
    languageId: "solutionLanguage",
    previewId: "solutionRenamePreview",
    errorId: "solutionNameError",
    buttonId: "solutionRenameButton",
  });
  updateModalEditorOptions();
  return valid;
}

export function renderSolutionMetaForm() {
  updateSolutionRenamePreview();
}
