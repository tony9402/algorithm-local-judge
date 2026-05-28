const app = window.AljApp;
const { state } = app;

/**
 * openModal 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} id 식별자입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function openModal(id) {
  app.optional("modalBackdrop")?.classList.remove("hidden");
  app.optional(id)?.classList.remove("hidden");
  if (id === "cacheModal") {
    app.renderCacheModalSummary(state.cache);
  }
}

/**
 * closeModals 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
function closeModals() {
  app.optional("modalBackdrop")?.classList.add("hidden");
  app.optional("packModal")?.classList.add("hidden");
  app.optional("cacheModal")?.classList.add("hidden");
}

Object.assign(app, {
  closeModals,
  openModal,
});
