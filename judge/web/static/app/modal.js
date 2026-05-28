const app = window.AljApp;
const { state } = app;

function openModal(id) {
  app.optional("modalBackdrop")?.classList.remove("hidden");
  app.optional(id)?.classList.remove("hidden");
  if (id === "cacheModal") {
    app.renderCacheModalSummary(state.cache);
  }
}

function closeModals() {
  app.optional("modalBackdrop")?.classList.add("hidden");
  app.optional("packModal")?.classList.add("hidden");
  app.optional("cacheModal")?.classList.add("hidden");
}

Object.assign(app, {
  closeModals,
  openModal,
});
