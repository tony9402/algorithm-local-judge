import { api } from "../api.js";
import { $, setText } from "../dom.js";
import {
  getEditorValue,
  resetVimTransientState,
  setEditorValue,
  updateDirtyState,
  updateEditorVisuals,
} from "../editor/core.js";
import { resetEditorHistory } from "../editor/history.js";
import { state } from "../state.js";
import {
  rememberSelectedFile,
  rememberView,
  selectionKey,
} from "../view-persistence.js";

const fileCallbacks = {
  confirmDiscardChanges: () => true,
  hasUnsavedChanges: () => false,
  isCurrentView: (seq) => seq === state.viewSeq,
  isReferenceSolutionPath: () => false,
  markAllSolutionsDirty: () => {},
  markFullTestDirty: () => {},
  markSolutionDirty: () => {},
  nextViewSeq: () => {
    state.viewSeq += 1;
    return state.viewSeq;
  },
  renderSolutionMetaForm: () => {},
  renderSolutionValidationSummary: () => {},
  renderTabFiles: () => {},
  setDirtySolutionPaths: () => {},
  showResult: () => {},
  solutionFilePaths: () => [],
};

export function configureFileActions(callbacks = {}) {
  Object.assign(fileCallbacks, callbacks);
}

export function apiFilePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

export function clearEditor(message = "작업 대상을 선택하세요.") {
  state.selectedFile = null;
  setEditorValue("", { clearHistory: true });
  state.lastSavedContent = "";
  resetEditorHistory();
  resetVimTransientState();
  setText("fileTitle", "파일 없음");
  setText("fileStatus", message);
  $("fileEditor").setAttribute("aria-label", "파일 편집기");
  updateEditorVisuals();
  fileCallbacks.renderSolutionMetaForm();
  fileCallbacks.renderSolutionValidationSummary();
}

export async function refreshProblemFiles(seq = state.viewSeq) {
  if (!state.selectedProblem) return;
  const data = await api(`/api/problems/${encodeURIComponent(state.selectedProblem)}/files`);
  if (!fileCallbacks.isCurrentView(seq)) return;
  state.files = data.files || [];
  fileCallbacks.renderTabFiles();
}

export async function openFile(path, refreshFiles = true, seq = null, skipConfirm = false) {
  const currentSeq = seq ?? fileCallbacks.nextViewSeq();
  if (!state.selectedProblem) return;
  if (path !== state.selectedFile && !skipConfirm && !fileCallbacks.confirmDiscardChanges?.()) return;
  rememberSelectedFile();
  setText("fileTitle", path);
  setText("fileStatus", "불러오는 중...");
  const data = await api(
    `/api/problems/${encodeURIComponent(state.selectedProblem)}/files/${apiFilePath(path)}`
  );
  if (!fileCallbacks.isCurrentView(currentSeq)) return;
  state.selectedFile = path;
  setEditorValue(data.content, { clearHistory: true });
  state.lastSavedContent = data.content;
  resetEditorHistory();
  resetVimTransientState();
  state.tabSelections[selectionKey()] = path;
  rememberView();
  setText("fileTitle", path);
  setText("fileStatus", "저장됨");
  $("fileEditor").setAttribute("aria-label", `${path} 파일 편집기`);
  updateEditorVisuals();
  updateDirtyState();
  if (refreshFiles) await refreshProblemFiles(currentSeq);
  fileCallbacks.renderTabFiles();
  fileCallbacks.renderSolutionMetaForm();
  fileCallbacks.renderSolutionValidationSummary();
}

export async function saveFile(options = {}) {
  if (!state.selectedProblem || !state.selectedFile) throw new Error("Open a file first.");
  const savedSolutionFile = state.selectedFile.startsWith("solutions/");
  const content = getEditorValue();
  await api(
    `/api/problems/${encodeURIComponent(state.selectedProblem)}/files/${apiFilePath(state.selectedFile)}`,
    {
      method: "PUT",
      body: JSON.stringify({ content }),
    }
  );
  state.lastSavedContent = content;
  setText("fileStatus", "저장됨");
  updateDirtyState();
  if (savedSolutionFile) {
    if (fileCallbacks.isReferenceSolutionPath(state.selectedFile)) {
      fileCallbacks.markAllSolutionsDirty("기준 정답 변경으로 모든 솔루션 재검증이 필요합니다.");
    } else {
      fileCallbacks.markSolutionDirty(
        state.selectedFile,
        `${state.selectedFile} 저장으로 솔루션 재검증이 필요합니다.`
      );
    }
  } else {
    if (
      state.selectedFile.startsWith("generator/")
      || state.selectedFile.startsWith("validator/")
      || state.selectedFile.startsWith("checker/")
    ) {
      fileCallbacks.setDirtySolutionPaths(fileCallbacks.solutionFilePaths());
    }
    fileCallbacks.markFullTestDirty(`${state.selectedFile} 저장으로 전체 테스트가 다시 필요합니다.`);
  }
  if (!options.silent) {
    fileCallbacks.showResult(`${state.selectedFile} 저장 완료`, "summary success");
  }
}

export async function saveOpenFileIfDirty() {
  if (!fileCallbacks.hasUnsavedChanges?.()) return false;
  await saveFile({ silent: true });
  fileCallbacks.showResult("변경사항을 저장한 뒤 실행합니다.", "summary success");
  return true;
}
