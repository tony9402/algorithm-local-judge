export const vimCallbacks = {
  /**
   * closeEditorCommandLine 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  closeEditorCommandLine: () => {},
  /**
   * openEditorCommandLine 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  openEditorCommandLine: () => {},
  /**
   * replaceEditorRange 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  replaceEditorRange: () => {},
  /**
   * updateEditorSettingsUi 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  updateEditorSettingsUi: () => {},
};

/**
 * configureEditorVim 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureEditorVim(callbacks = {}) {
  Object.assign(vimCallbacks, callbacks);
}

/**
 * replaceEditorRange 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} editor `editor` 값입니다.
 * @param {any} start `start` 값입니다.
 * @param {any} end `end` 값입니다.
 * @param {any} replacement `replacement` 값입니다.
 * @param {any} cursorPosition `cursorPosition` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function replaceEditorRange(editor, start, end, replacement, cursorPosition = start + replacement.length) {
  vimCallbacks.replaceEditorRange(editor, start, end, replacement, cursorPosition);
}
