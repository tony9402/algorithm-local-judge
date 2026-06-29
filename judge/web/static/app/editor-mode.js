/**
 * 편집기 mode 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;

function clearSourceInputs() {
  const fileInput = app.optional("sourceFileInput");
  const filenameInput = app.optional("filenameInput");
  const sourceTextInput = app.optional("sourceTextInput");
  if (fileInput) fileInput.value = "";
  if (filenameInput) filenameInput.value = "";
  if (sourceTextInput) sourceTextInput.value = "";
  app.updateLanguageBadge();
  app.updateEditorView();
  app.syncEditorScroll();
}
/**
 * mode 값을 내부 상태나 DOM 요소에 반영합니다.
 *
 * @param {string} mode mode을 계산하거나 검증할 때 필요한 mode 입력입니다.
 */
function setMode(mode) {
  state.sourceMode = "text";
  app.$("uploadModeButton").classList.toggle("active", false);
  app.$("textModeButton").classList.toggle("active", true);
  app.$("uploadModeButton").setAttribute("aria-selected", "false");
  app.$("textModeButton").setAttribute("aria-selected", "true");
  app.$("uploadSourcePanel").classList.add("hidden");
  app.$("textSourcePanel").classList.remove("hidden");
  app.updateLanguageBadge();
}

async function loadSourceFileIntoEditor() {
  const input = app.optional("sourceFileInput");
  const file = input?.files?.[0];
  if (!file) {
    app.updateLanguageBadge();
    return;
  }
  app.$("filenameInput").value = file.name;
  app.$("sourceTextInput").value = await file.text();
  setMode("text");
  app.updateEditorView();
  app.syncEditorScroll();
}
/**
 * drop zone 이벤트를 DOM 요소와 핸들러에 연결합니다.
 */
function bindDropZone() {
  const zone = app.$("uploadSourcePanel");
  const input = app.$("sourceFileInput");
  for (const eventName of ["dragenter", "dragover"]) {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.add("drag-over");
    });
  }
  for (const eventName of ["dragleave", "drop"]) {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.remove("drag-over");
    });
  }
  zone.addEventListener("drop", (event) => {
    const files = event.dataTransfer?.files;
    if (files?.length) {
      input.files = files;
      void app.withErrors(loadSourceFileIntoEditor);
    }
  });
}

Object.assign(app, {
  bindDropZone,
  clearSourceInputs,
  loadSourceFileIntoEditor,
  setMode,
});
