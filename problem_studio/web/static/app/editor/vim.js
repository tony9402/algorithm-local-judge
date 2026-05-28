/**
 * vim 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { state } from "../state.js";
import { redoEditorChange, undoEditorChange } from "./history.js";
import {
  currentLineBounds,
  firstTextColumn,
  lineEndAt,
  lineStartAt,
  normalCursorEndAt,
  totalLineCount,
} from "./position.js";
import {
  enterVimVisualMode,
  exitVimVisualMode,
  isVimVisualMode,
  moveEditorCursor,
  moveEditorHorizontal,
  moveEditorVertical,
} from "./selection.js";
import { setVimMode } from "./vim-mode.js";
import {
  applyVimOperator,
  changeToLineEnd,
  clearVimPending,
  deleteToLineEnd,
  deleteVimChar,
  findVimSearch,
  handleVimVisualKey,
  insertVimLine,
  joinVimLines,
  moveToLine,
  moveToNextWord,
  moveToPreviousWord,
  moveToWordEnd,
  pasteVimRegister,
  replaceVimChar,
  vimCountValue,
} from "./vim-operations.js";
import { vimCallbacks } from "./vim-context.js";

export { configureEditorVim } from "./vim-context.js";
export {
  editorModeBadgeText,
  resetVimTransientState,
  setVimMode,
} from "./vim-mode.js";
export { findVimSearch } from "./vim-operations.js";
export function handleVimKeydown(event) {
  if (state.editorMode !== "vim") return false;
  const editor = event.currentTarget;
  const key = event.key;
  if (event.isComposing || event.keyCode === 229) {
    if (state.vimMode !== "insert") {
      event.preventDefault();
      event.stopPropagation();
      return true;
    }
    return false;
  }
  if (key === "Escape" || (event.ctrlKey && key === "[")) {
    event.preventDefault();
    event.stopPropagation();
    if (state.vimMode === "insert") {
      setVimMode("normal", editor, { fromInsert: true });
    } else if (isVimVisualMode()) {
      exitVimVisualMode(editor);
    } else {
      clearVimPending();
    }
    return true;
  }
  if (state.vimMode === "insert") return false;
  if (event.ctrlKey && key.toLowerCase() === "r") {
    event.preventDefault();
    event.stopPropagation();
    redoEditorChange(editor);
    return true;
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return false;

  const { value, selectionStart } = editor;
  const prevent = () => {
    event.preventDefault();
    event.stopPropagation();
  };

  prevent();

  if (/^[1-9]$/.test(key) || (key === "0" && state.vimCount)) {
    state.vimCount += key;
    vimCallbacks.updateEditorSettingsUi();
    return true;
  }

  if (isVimVisualMode()) {
    return handleVimVisualKey(editor, key);
  }

  if (state.vimPending === "r") {
    replaceVimChar(editor, key);
    clearVimPending();
    return true;
  }
  if (["d", "y", "c"].includes(state.vimPending)) {
    return applyVimOperator(editor, key);
  }
  if (state.vimPending === "g") {
    if (key === "g") {
      moveToLine(editor, state.vimOperatorCount);
      clearVimPending();
      return true;
    }
    clearVimPending();
    return true;
  }

  const count = () => vimCountValue(1);

  if (key === "i") {
    setVimMode("insert", editor);
  } else if (key === "a") {
    moveEditorCursor(editor, Math.min(selectionStart + 1, lineEndAt(value, selectionStart)), null, {
      normal: false,
    });
    setVimMode("insert", editor);
  } else if (key === "I") {
    const { start, end } = currentLineBounds(value, selectionStart);
    moveEditorCursor(editor, firstTextColumn(value, start, end), null, { normal: false });
    setVimMode("insert", editor);
  } else if (key === "A") {
    moveEditorCursor(editor, lineEndAt(value, selectionStart), null, { normal: false });
    setVimMode("insert", editor);
  } else if (key === "o") {
    insertVimLine(editor, false);
  } else if (key === "O") {
    insertVimLine(editor, true);
  } else if (key === "v") {
    enterVimVisualMode(editor, "visual");
  } else if (key === "V") {
    enterVimVisualMode(editor, "visual-line");
  } else if (key === "h" || key === "ArrowLeft") {
    moveEditorHorizontal(editor, -count());
  } else if (key === "l" || key === "ArrowRight") {
    moveEditorHorizontal(editor, count());
  } else if (key === "j" || key === "ArrowDown") {
    const amount = count();
    for (let index = 0; index < amount; index += 1) moveEditorVertical(editor, 1);
  } else if (key === "k" || key === "ArrowUp") {
    const amount = count();
    for (let index = 0; index < amount; index += 1) moveEditorVertical(editor, -1);
  } else if (key === "0" || key === "Home") {
    moveEditorCursor(editor, lineStartAt(value, selectionStart));
  } else if (key === "^") {
    const { start, end } = currentLineBounds(value, selectionStart);
    moveEditorCursor(editor, firstTextColumn(value, start, end));
  } else if (key === "$" || key === "End") {
    moveEditorCursor(editor, normalCursorEndAt(value, selectionStart));
  } else if (key === "w") {
    moveToNextWord(editor, count());
  } else if (key === "e") {
    moveToWordEnd(editor, count());
  } else if (key === "b") {
    moveToPreviousWord(editor, count());
  } else if (key === "g") {
    state.vimPending = "g";
    state.vimOperatorCount = vimCountValue(1);
  } else if (key === "G") {
    moveToLine(editor, state.vimCount ? vimCountValue(1) : totalLineCount(value));
  } else if (key === "x" || key === "Delete") {
    const amount = count();
    for (let index = 0; index < amount; index += 1) deleteVimChar(editor);
  } else if (key === "d" || key === "y" || key === "c") {
    state.vimPending = key;
    state.vimOperatorCount = vimCountValue(1);
  } else if (key === "D") {
    deleteToLineEnd(editor);
  } else if (key === "C") {
    changeToLineEnd(editor);
  } else if (key === "r") {
    state.vimPending = "r";
  } else if (key === "s") {
    deleteVimChar(editor);
    setVimMode("insert", editor, { recordHistory: false });
  } else if (key === "p") {
    pasteVimRegister(editor, false, count());
  } else if (key === "P") {
    pasteVimRegister(editor, true, count());
  } else if (key === "J") {
    joinVimLines(editor, count());
  } else if (key === "u") {
    state.vimCount = "";
    undoEditorChange(editor);
  } else if (key === "/") {
    state.vimCount = "";
    vimCallbacks.openEditorCommandLine("search");
  } else if (key === ":") {
    state.vimCount = "";
    vimCallbacks.openEditorCommandLine("command");
  } else if (key === "n") {
    state.vimCount = "";
    findVimSearch(editor, state.vimSearchDirection || 1);
  } else if (key === "N") {
    state.vimCount = "";
    findVimSearch(editor, -(state.vimSearchDirection || 1));
  } else {
    clearVimPending();
    return true;
  }
  if (!["d", "g", "y", "c", "r"].includes(key)) clearVimPending();
  else vimCallbacks.updateEditorSettingsUi();
  return true;
}
