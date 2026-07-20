/** First-viewport connection recovery and isolated secondary-region errors. */

const app = window.AljApp;
const { state } = app;

const REGION_TARGETS = {
  packs: ".sidebar-packs",
  cache: ".sidebar-cache",
  sources: ".source-history",
  "recent-submissions": ".recent-submissions",
  submissions: ".submissions-master",
};

const REGION_LABELS = {
  packs: "문제 팩",
  cache: "캐시",
  sources: "이전 코드",
  "recent-submissions": "최근 제출",
  submissions: "제출 기록",
};

function errorMessage(error) {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "알 수 없는 오류가 발생했습니다.";
}

function setConnectionPending() {
  const retry = app.optional("connectionRetryButton");
  if (retry) retry.disabled = state.connectionRetrying;
}

function setConnectionConnected() {
  app.optional("connectionBanner")?.classList.add("hidden");
  const retry = app.optional("connectionRetryButton");
  if (retry) {
    retry.disabled = false;
    retry.textContent = "다시 연결";
  }
}

function showConnectionError(error) {
  const banner = app.optional("connectionBanner");
  if (!banner) return;
  app.setText("connectionBannerMessage", errorMessage(error));
  banner.classList.remove("hidden");
  const retry = app.optional("connectionRetryButton");
  if (retry) {
    retry.disabled = false;
    retry.textContent = "다시 연결";
  }
}

function secondaryErrorId(region) {
  return `secondary-error-${region}`;
}

function clearSecondaryError(region) {
  document.getElementById(secondaryErrorId(region))?.remove();
  delete state.secondaryErrors[region];
}

function showSecondaryError(region, error) {
  const selector = REGION_TARGETS[region];
  const target = selector ? document.querySelector(selector) : null;
  if (!target) return;
  state.secondaryErrors[region] = errorMessage(error);
  let notice = document.getElementById(secondaryErrorId(region));
  if (!notice) {
    notice = document.createElement("div");
    notice.id = secondaryErrorId(region);
    notice.className = "secondary-error";
    notice.setAttribute("role", "alert");
    const message = document.createElement("span");
    message.className = "secondary-error-message";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.textContent = "다시 시도";
    retry.setAttribute("data-secondary-retry", region);
    notice.append(message, retry);
    target.prepend(notice);
  }
  const message = notice.querySelector(".secondary-error-message");
  if (message) {
    message.textContent = `${REGION_LABELS[region] || region}을(를) 불러오지 못했습니다: ${state.secondaryErrors[region]}`;
  }
}

async function retryConnection() {
  if (state.connectionRetrying) return;
  state.connectionRetrying = true;
  const retry = app.optional("connectionRetryButton");
  if (retry) {
    retry.disabled = true;
    retry.textContent = "연결 중…";
  }
  try {
    await app.refresh();
  } catch (error) {
    app.showError(errorMessage(error));
  } finally {
    state.connectionRetrying = false;
    if (!app.optional("connectionBanner")?.classList.contains("hidden") && retry) {
      retry.disabled = false;
      retry.textContent = "다시 연결";
    }
  }
}

function bindConnectionEvents() {
  app.on("connectionRetryButton", "click", retryConnection);
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest("[data-secondary-retry]");
    const region = button?.getAttribute("data-secondary-retry");
    if (!region || button.disabled) return;
    button.disabled = true;
    void app.refreshSecondaryRegion(region).finally(() => {
      if (button.isConnected) button.disabled = false;
    });
  });
}

Object.assign(app, {
  bindConnectionEvents,
  clearSecondaryError,
  errorMessage,
  retryConnection,
  setConnectionConnected,
  setConnectionPending,
  showConnectionError,
  showSecondaryError,
});
