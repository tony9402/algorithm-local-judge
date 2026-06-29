/**
 * visuals 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { $, optional, setText } from "../dom.js";
import { state } from "../state.js";
import {
  editorCursorOffset,
  getEditorValue,
  updateCodeMirrorOptions,
} from "./codemirror.js";
import { highlightCode, languageForPath } from "./highlight.js";
import { editorLineColumn } from "./position.js";
import { isVimVisualMode, vimModeClassName } from "./selection.js";
import { editorModeBadgeText } from "./vim.js";
/**
 * 편집기 visuals 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
export function updateEditorVisuals() {
  if (state.codeMirror) {
    updateCodeMirrorOptions();
    updateEditorStatus();
    return;
  }
  const editor = $("fileEditor");
  const language = languageForPath(state.selectedFile);
  $("codeEditor").dataset.language = language;
  const text = editor.value || "";
  $("codeHighlight").innerHTML = highlightCode(text, language) + "\n";
  const lineCount = Math.max(1, text.split("\n").length);
  $("editorLineNumbers").textContent = Array.from({ length: lineCount }, (_, index) => index + 1).join("\n");
  syncEditorScroll();
  updateEditorStatus();
}
export function syncEditorScroll() {
  if (state.codeMirror) return;
  const editor = $("fileEditor");
  $("codeHighlight").scrollTop = editor.scrollTop;
  $("codeHighlight").scrollLeft = editor.scrollLeft;
  $("editorLineNumbers").scrollTop = editor.scrollTop;
}
/**
 * 편집기 cursor visible 조건을 확인하고 위반 시 호출자가 중단할 수 있는 예외를 발생시킵니다.
 *
 * @param {any} editor 편집기 cursor visible을 계산하거나 검증할 때 필요한 편집기 입력입니다.
 */
export function ensureEditorCursorVisible(editor) {
  if (state.codeMirror) {
    state.codeMirror.scrollIntoView(state.codeMirror.getCursor(), 48);
    return;
  }
  const cursorPosition = isVimVisualMode()
    ? state.vimVisualCursor ?? editor.selectionStart
    : editor.selectionStart;
  const { line, column } = editorLineColumn(editor.value || "", cursorPosition || 0);
  const styles = window.getComputedStyle(editor);
  const lineHeight = Number.parseFloat(styles.lineHeight) || 20;
  const fontSize = Number.parseFloat(styles.fontSize) || 13;
  const charWidth = fontSize * 0.62;
  const targetTop = Math.max(0, (line - 1) * lineHeight);
  const visibleBottom = editor.scrollTop + editor.clientHeight;
  if (targetTop < editor.scrollTop) {
    editor.scrollTop = Math.max(0, targetTop - lineHeight);
  } else if (targetTop + lineHeight > visibleBottom) {
    editor.scrollTop = Math.max(0, targetTop - editor.clientHeight + lineHeight * 2);
  }
  const targetLeft = Math.max(0, column * charWidth);
  const visibleRight = editor.scrollLeft + editor.clientWidth;
  if (targetLeft < editor.scrollLeft) {
    editor.scrollLeft = Math.max(0, targetLeft - charWidth * 2);
  } else if (targetLeft + charWidth > visibleRight) {
    editor.scrollLeft = Math.max(0, targetLeft - editor.clientWidth + charWidth * 4);
  }
  syncEditorScroll();
}

function languageLabelForPath(path) {
  const language = languageForPath(path);
  return {
    cpp: "C++",
    python: "Python",
    pypy: "PyPy",
    java: "Java",
    json: "JSON",
    yaml: "YAML",
    text: "Text",
  }[language] || "Text";
}
function commandStatusText() {
  if (state.editorMode !== "vim") return "";
  const count = state.vimCount ? state.vimCount : "";
  const pending = state.vimPending ? `${state.vimPending}...` : "";
  const visual = isVimVisualMode() ? "visual selection" : "";
  const prefix = [count, pending].filter(Boolean).join(" ");
  return [prefix, visual, state.vimMessage].filter(Boolean).join(" · ");
}
/**
 * 편집기 상태 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
export function updateEditorStatus() {
  const editor = optional("fileEditor");
  if (!editor) return;
  const value = getEditorValue();
  const cursorPosition = state.codeMirror
    ? editorCursorOffset()
    : isVimVisualMode()
      ? state.vimVisualCursor ?? editor.selectionStart
      : editor.selectionStart;
  const position = editorLineColumn(value || "", cursorPosition || 0);
  const mode = state.editorMode === "vim" ? editorModeBadgeText() : "기본";
  const dirty = state.selectedFile && value !== state.lastSavedContent ? "수정됨" : "저장됨";
  const percent =
    value.length > 0
      ? `${Math.round(((cursorPosition || 0) / value.length) * 100)}%`
      : "0%";
  setText("editorStatusMode", mode);
  setText("editorStatusPosition", `${dirty} · Ln ${position.line}, Col ${position.column + 1}`);
  setText("editorStatusCommand", commandStatusText());
  setText("editorStatusSearch", state.vimSearchQuery ? `/${state.vimSearchQuery}` : "");
  setText("editorStatusFile", `${languageLabelForPath(state.selectedFile)} · 4 spaces · ${percent}`);
  const statusMode = optional("editorStatusMode");
  if (statusMode) {
    statusMode.className = `editor-status-mode ${
      state.editorMode === "vim" ? `vim-${vimModeClassName()}` : ""
    }`.trim();
  }
}
