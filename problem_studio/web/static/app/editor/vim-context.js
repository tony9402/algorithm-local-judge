/**
 * vim context 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

export const vimCallbacks = {
  closeEditorCommandLine: () => {},
  openEditorCommandLine: () => {},
  replaceEditorRange: () => {},
  updateEditorSettingsUi: () => {},
};
export function configureEditorVim(callbacks = {}) {
  Object.assign(vimCallbacks, callbacks);
}
export function replaceEditorRange(editor, start, end, replacement, cursorPosition = start + replacement.length) {
  vimCallbacks.replaceEditorRange(editor, start, end, replacement, cursorPosition);
}
