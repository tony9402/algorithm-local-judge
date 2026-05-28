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
