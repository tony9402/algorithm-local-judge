import { $, setText } from "../dom.js";
import { updateModalEditorOptions } from "../editor/codemirror.js";
import { EXTENSIONS, SAFE_SOLUTION_NAME } from "../state.js";

/**
 * formatSolutionFilename 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} name 이름입니다.
 * @param {any} expected `expected` 값입니다.
 * @param {any} language `language` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function formatSolutionFilename(name, expected, language) {
  const normalizedName = name.trim().replaceAll(" ", "_") || "solution";
  return `${normalizedName}.${expected}${EXTENSIONS[language] || ".cpp"}`;
}

/**
 * solutionNameError 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function solutionNameError(value) {
  const name = value.trim().replaceAll(" ", "_");
  if (!name) return "솔루션 이름을 입력하세요.";
  if (!SAFE_SOLUTION_NAME.test(name)) return "영문, 숫자, _, -, . 만 사용할 수 있습니다.";
  return "";
}

/**
 * updateSolutionFormValidity 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} config 동작 설정입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * updateSolutionPreview 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * updateSolutionRenamePreview 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * renderSolutionMetaForm 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function renderSolutionMetaForm() {
  updateSolutionRenamePreview();
}
