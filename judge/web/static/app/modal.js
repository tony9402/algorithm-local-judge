/**
 * 모달 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;
/**
 * 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 *
 * @param {any} id 모달을 계산하거나 검증할 때 필요한 ID 입력입니다.
 */
function openModal(id) {
  app.optional("modalBackdrop")?.classList.remove("hidden");
  app.optional(id)?.classList.remove("hidden");
  if (id === "cacheModal") {
    app.renderCacheModalSummary(state.cache);
  }
}
/**
 * modals 모달이나 열린 상태를 닫고 관련 임시 상태를 정리합니다.
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
