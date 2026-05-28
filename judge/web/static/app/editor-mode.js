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

function setMode(mode) {
  state.sourceMode = mode;
  app.$("uploadModeButton").classList.toggle("active", mode === "upload");
  app.$("textModeButton").classList.toggle("active", mode === "text");
  app.$("uploadModeButton").setAttribute("aria-selected", String(mode === "upload"));
  app.$("textModeButton").setAttribute("aria-selected", String(mode === "text"));
  app.$("uploadSourcePanel").classList.toggle("hidden", mode !== "upload");
  app.$("textSourcePanel").classList.toggle("hidden", mode !== "text");
  app.updateLanguageBadge();
}

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
      setMode("upload");
      app.updateLanguageBadge();
    }
  });
}

Object.assign(app, {
  bindDropZone,
  clearSourceInputs,
  setMode,
});
