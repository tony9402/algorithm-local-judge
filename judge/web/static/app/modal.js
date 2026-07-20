/**
 * 모달 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;

let activeModalId = null;
let modalReturnFocus = null;
let modalReturnScroll = 0;
const FOCUSABLE = [
  "button:not([disabled])",
  "[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "summary",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function setAppInert(isInert) {
  const shell = document.querySelector(".shell");
  if (!shell) return;
  if (isInert) {
    shell.setAttribute("inert", "");
    shell.setAttribute("aria-hidden", "true");
  } else {
    shell.removeAttribute("inert");
    shell.removeAttribute("aria-hidden");
  }
}

function focusFirstModalControl(modal) {
  const focusable = [...modal.querySelectorAll(FOCUSABLE)]
    .filter((element) => element instanceof HTMLElement && element.offsetParent !== null);
  const preferred = modal.querySelector("[data-modal-autofocus]");
  const target = preferred instanceof HTMLElement && preferred.offsetParent !== null
    ? preferred
    : focusable[0] || modal;
  window.setTimeout(() => target.focus(), 0);
}

/**
 * 모달 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.
 *
 * @param {any} id 모달을 계산하거나 검증할 때 필요한 ID 입력입니다.
 */
function openModal(id) {
  const modal = app.optional(id);
  if (!modal) return;
  if (id !== "jobsPanel") app.closeJobsForOverlay?.();
  modalReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  modalReturnScroll = window.scrollY;
  activeModalId = id;
  app.optional("modalBackdrop")?.classList.remove("hidden");
  modal.classList.remove("hidden");
  modal.setAttribute("tabindex", "-1");
  document.documentElement.classList.add("modal-open");
  document.body.classList.add("modal-open");
  setAppInert(true);
  if (id === "cacheModal") {
    app.renderCacheModalSummary(state.cache);
  }
  focusFirstModalControl(modal);
}
/**
 * modals 모달이나 열린 상태를 닫고 관련 임시 상태를 정리합니다.
 */
function closeModals() {
  const closingModalId = activeModalId;
  app.optional("modalBackdrop")?.classList.add("hidden");
  app.optional("packModal")?.classList.add("hidden");
  app.optional("cacheModal")?.classList.add("hidden");
  app.optional("problemPickerModal")?.classList.add("hidden");
  app.optional("problemFolderMoveModal")?.classList.add("hidden");
  app.optional("resultModal")?.classList.add("hidden");
  app.optional("submissionsDrawer")?.classList.add("hidden");
  if (closingModalId === "jobsPanel") app.optional("jobsPanel")?.classList.add("hidden");
  app.onSubmissionsClosed?.();
  if (closingModalId === "problemPickerModal") app.onProblemPickerClosed?.();
  if (closingModalId === "problemFolderMoveModal") app.onProblemFolderMoveClosed?.();
  if (closingModalId === "jobsPanel") app.onJobsOverlayClosed?.();
  activeModalId = null;
  document.documentElement.classList.remove("modal-open");
  document.body.classList.remove("modal-open");
  setAppInert(false);
  const returnScroll = modalReturnScroll;
  modalReturnScroll = 0;
  const target = modalReturnFocus;
  modalReturnFocus = null;
  window.scrollTo(0, returnScroll);
  if (target && document.contains(target)) target.focus();
}

function hasActiveModal() {
  return Boolean(activeModalId);
}

function handleModalKeydown(event) {
  if (!activeModalId) return false;
  if (event.key === "Escape") {
    closeModals();
    event.preventDefault();
    return true;
  }
  if (event.key !== "Tab") return false;
  const modal = app.optional(activeModalId);
  if (!modal || modal.classList.contains("hidden")) return false;
  const focusable = [...modal.querySelectorAll(FOCUSABLE)]
    .filter((element) => element instanceof HTMLElement && element.offsetParent !== null);
  if (!focusable.length) {
    event.preventDefault();
    modal.focus();
    return true;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
    return true;
  }
  if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
    return true;
  }
  return false;
}

Object.assign(app, {
  closeModals,
  hasActiveModal,
  handleModalKeydown,
  openModal,
});
