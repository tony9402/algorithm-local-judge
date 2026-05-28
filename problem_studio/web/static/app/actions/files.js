/**
 * 파일 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

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
/**
 * 편집기 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.
 *
 * @param {string} message 사용자에게 표시하거나 커밋/진행 상태에 기록할 메시지입니다.
 */
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
/**
 * 문제 파일 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
 *
 * @param {any} seq 문제 파일을 계산하거나 검증할 때 필요한 seq 입력입니다.
 */
export async function refreshProblemFiles(seq = state.viewSeq) {
  if (!state.selectedProblem) return;
  const data = await api(`/api/problems/${encodeURIComponent(state.selectedProblem)}/files`);
  if (!fileCallbacks.isCurrentView(seq)) return;
  state.files = data.files || [];
  fileCallbacks.renderTabFiles();
}
/**
 * 파일 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 *
 * @param {string} path 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
 * @param {Array} refreshFiles 파일을 계산하거나 검증할 때 필요한 refresh 파일 입력입니다.
 * @param {any} seq 파일을 계산하거나 검증할 때 필요한 seq 입력입니다.
 * @param {any} skipConfirm 파일을 계산하거나 검증할 때 필요한 skip confirm 입력입니다.
 */
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
/**
 * 파일 데이터를 다음 요청에서도 사용할 수 있도록 안전한 위치에 저장합니다.
 *
 * @param {object} options 호출자가 동작 일부를 조정하기 위해 넘기는 선택 옵션 묶음입니다.
 */
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
