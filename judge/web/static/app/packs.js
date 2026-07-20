/**
 * 문제팩 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;
let retryPackAction = null;

function renderPacksDisclosure() {
  const toggle = app.optional("packSectionToggle");
  const list = app.optional("packList");
  if (!toggle || !list) return;
  toggle.setAttribute("aria-expanded", String(state.packsExpanded));
  list.classList.toggle("hidden", !state.packsExpanded);
  const chevron = toggle.querySelector(".sidebar-section-chevron");
  if (chevron) chevron.textContent = state.packsExpanded ? "▾" : "▸";
}

function togglePacksDisclosure() {
  state.packsExpanded = !state.packsExpanded;
  renderPacksDisclosure();
}

function installLabel(result) {
  const target = result.assetName || result.label || result.installedPath || "설치된 문제";
  if (result.installType === "source") {
    return `소스 fallback 설치 완료: ${target}`;
  }
  const security = [];
  if (result.checksumVerified) security.push("체크섬 확인됨");
  if (result.signatureVerified) security.push("게시자 서명 확인됨");
  if (result.signatureVerified === false) security.push("로컬 신뢰 파일 · 게시자 서명 미검증");
  return `문제 팩 설치 완료: ${target}${security.length ? ` · ${security.join(" · ")}` : ""}`;
}

function officialPackErrorMessage(error) {
  const detail = String(error?.message || "알 수 없는 오류");
  const lower = detail.toLowerCase();
  if (detail.startsWith("공식 문제 설치 실패:")) return detail;
  if (error?.status === 403 || lower.includes("rate limit")) {
    return `공식 문제 설치 실패: GitHub rate limit 또는 권한 문제로 요청이 막혔습니다. 잠시 후 다시 시도하거나 ref를 지정하거나 내려받은 .aljpack을 설치하세요. 상세: ${detail}`;
  }
  if (error?.status === 404 || lower.includes("not found")) {
    return `공식 문제 설치 실패: repository, ref 또는 release asset을 찾지 못했습니다. 저장소, branch/tag, asset 이름을 확인하세요. 상세: ${detail}`;
  }
  if (lower.includes("untrusted repository")) {
    return `공식 문제 설치 실패: 신뢰한 저장소가 아닙니다. judge pack trust add owner/name으로 추가하거나 기본 신뢰 저장소를 사용하세요. 상세: ${detail}`;
  }
  if (lower.includes("checksum")) {
    return `공식 문제 설치 실패: release checksum 검증에 실패했습니다. 배포자에게 일치하는 .sha256 파일 업로드를 요청하세요. 상세: ${detail}`;
  }
  if (lower.includes("sigstore") || lower.includes("signature") || lower.includes("cosign")) {
    return "공식 문제 설치 실패: 게시자 서명을 검증하지 못했습니다. 앱을 업데이트한 뒤 다시 시도하거나 배포자에게 서명 파일 상태를 문의하세요.";
  }
  if (lower.includes("aljpack") || lower.includes("asset")) {
    return `공식 문제 설치 실패: 현재 플랫폼에 맞는 .aljpack asset이 없습니다. asset 이름을 지정하거나 신뢰한 저장소에서만 source fallback을 사용하세요. 상세: ${detail}`;
  }
  if (lower.includes("platform")) {
    return `공식 문제 설치 실패: 선택한 팩이 현재 플랫폼과 맞지 않습니다. 이 OS/CPU용 팩을 선택하세요. 상세: ${detail}`;
  }
  return `공식 문제 설치 실패: ${detail}`;
}

function setPackProgress(value, label) {
  const progress = app.optional("packProgress");
  if (!progress) return;
  const normalized = Math.max(0, Math.min(100, Number(value) || 0));
  progress.classList.remove("hidden");
  progress.setAttribute("aria-valuenow", String(normalized));
  progress.setAttribute("aria-valuetext", label);
  app.setText("packProgressText", `${normalized}%`);
  const fill = app.optional("packProgressFill");
  if (fill) fill.style.width = `${normalized}%`;
}

function setPackStatus(message, className = "modal-status") {
  const status = app.optional("packStatus");
  if (!status) return;
  status.textContent = message;
  status.className = className;
}

function onPackQueued(job) {
  state.activePackJobId = job.jobId;
  app.optional("packJobsButton")?.classList.remove("hidden");
  setPackProgress(12, `${job.title || "문제 팩 설치"} 대기 중`);
  setPackStatus("설치 작업이 대기열에 추가되었습니다. 이 창에서 진행 상황을 확인할 수 있습니다.");
}

function packJobPercent(job) {
  const current = Number(job.progress?.current);
  const total = Number(job.progress?.total);
  if (Number.isFinite(current) && Number.isFinite(total) && total > 0) {
    return Math.round((current / total) * 100);
  }
  return ["succeeded", "failed", "cancelled", "stale"].includes(job.status) ? 100 : 36;
}

function renderPackJobProgress(jobList) {
  if (!state.activePackJobId) return;
  const job = jobList.find((item) => item.jobId === state.activePackJobId);
  if (!job) return;
  const status = {
    queued: "대기 중",
    running: "설치 중",
    cancelling: "취소 요청됨",
    succeeded: "설치 완료",
    failed: "설치 실패",
    cancelled: "설치 취소됨",
    stale: "작업 만료됨",
  }[job.status] || job.status;
  setPackProgress(packJobPercent(job), `${job.title || "문제 팩 설치"} ${status}`);
  if (["queued", "running", "cancelling"].includes(job.status)) {
    setPackStatus(job.progress?.message || `${job.title || "문제 팩"} ${status}`);
  }
}

function verifyOfficialInstall(result, requireSignedPack) {
  if (!requireSignedPack && result.installType === "source") return;
  if (
    result.installType !== "pack"
    || result.checksumVerified !== true
    || result.signatureVerified !== true
  ) {
    throw new Error(
      "공식 문제 설치 실패: 체크섬과 게시자 서명이 모두 확인된 .aljpack만 설치할 수 있습니다."
    );
  }
}

async function runPackAction(action, pendingMessage, errorMessage = (error) => error.message) {
  retryPackAction = () => runPackAction(action, pendingMessage, errorMessage);
  app.optional("packRetryButton")?.classList.add("hidden");
  app.optional("packJobsButton")?.classList.add("hidden");
  state.activePackJobId = null;
  setPackProgress(8, pendingMessage);
  setPackStatus(pendingMessage);
  try {
    const result = await action();
    setPackProgress(100, "문제 팩 설치 완료");
    setPackStatus(installLabel(result), "modal-status success");
    app.clearSampleCache();
    await app.refresh();
    return result;
  } catch (error) {
    const message = errorMessage(error);
    setPackProgress(100, "문제 팩 설치 실패");
    setPackStatus(message, "modal-status error");
    app.optional("packRetryButton")?.classList.remove("hidden");
    throw new Error(message);
  } finally {
    updatePackActionState();
  }
}
/**
 * 문제팩 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {Array} packs 문제팩을 계산하거나 검증할 때 필요한 문제팩 입력입니다.
 */
function renderPacks(packs) {
  const list = app.$("packList");
  list.innerHTML = "";
  if (!packs.length) {
    list.textContent = "설치된 문제 팩이 없습니다.";
    list.classList.add("muted");
    renderPacksDisclosure();
    return;
  }
  list.classList.remove("muted");
  for (const pack of packs) {
    const item = document.createElement("div");
    item.className = "list-item";
    const platforms = (pack.supportedPlatforms || []).join(", ");
    const problemIds = Array.isArray(pack.problems) ? pack.problems : [];
    const problems = problemIds.join(", ");
    const packLabel = `${app.escapeHtml(pack.packId)} ${app.escapeHtml(pack.version || "")}`;
    item.innerHTML = `<strong>${packLabel}</strong><span>${app.escapeHtml(platforms)} · 문제 ${problemIds.length}개${problems ? ` · ${app.escapeHtml(problems)}` : ""}</span>`;
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "danger secondary compact";
    removeButton.textContent = "이 팩 제거";
    removeButton.setAttribute(
      "aria-label",
      `${pack.packId} 문제 팩 설치본과 포함 문제 복사본 ${problemIds.length}개 제거`
    );
    removeButton.addEventListener("click", () => {
      void app.withErrors(() => removeInstalledPack(pack, removeButton));
    });
    item.appendChild(removeButton);
    list.appendChild(item);
  }
  renderPacksDisclosure();
}

async function removeInstalledPack(pack, trigger) {
  const packId = String(pack.packId || "");
  const problemIds = Array.isArray(pack.problems) ? pack.problems : [];
  const confirmation = window.prompt(
    `${packId} 문제 팩 설치본과 포함 문제 복사본 ${problemIds.length}개를 제거합니다.\n`
      + `같은 ID의 문제가 다른 소스에 있으면 Judge 목록에는 계속 표시될 수 있습니다.\n`
      + `사용자 제출 기록과 코드는 유지됩니다. 계속하려면 문제 팩 ID를 입력하세요.`,
    ""
  );
  if (confirmation === null) return;
  if (confirmation !== packId) {
    app.showToast("문제 팩 ID가 일치하지 않아 제거하지 않았습니다.", "error");
    trigger?.focus();
    return;
  }
  if (trigger) trigger.disabled = true;
  let removed = false;
  let focusRestored = false;
  try {
    const result = await app.api(`/api/packs/${encodeURIComponent(packId)}`, {
      method: "DELETE",
      body: JSON.stringify({ confirm_pack_id: confirmation }),
    });
    removed = true;
    app.clearSampleCache();
    await app.refresh();
    app.showToast(
      `${packId} 문제 팩 설치본과 포함 문제 복사본 ${result.removedProblemCount || 0}개를 제거했습니다.`
    );
    app.optional("packSectionToggle")?.focus();
    focusRestored = true;
  } finally {
    if (trigger?.isConnected) trigger.disabled = false;
    if (!focusRestored) {
      const focusTarget = removed ? app.optional("packSectionToggle") : trigger;
      focusTarget?.focus();
    }
  }
}
/**
 * 업로드 문제팩 장시간 작업을 큐에 등록하고 UI가 추적할 작업 상태를 구성합니다.
 */
async function uploadPack() {
  const file = app.$("packFileInput").files[0];
  if (!file) throw new Error("문제 팩 파일이 필요합니다.");
  return runPackAction(async () => {
    const formData = new FormData();
    formData.append("file", file);
    return app.runQueuedJob("/api/packs/upload/jobs", {
      method: "POST",
      body: formData,
      onQueued: onPackQueued,
    });
  }, "업로드한 문제 팩을 설치하는 중...");
}
/**
 * 다운로드 official 문제팩 장시간 작업을 큐에 등록하고 UI가 추적할 작업 상태를 구성합니다.
 */
async function downloadOfficialPack({ advanced = true } = {}) {
  const repository = advanced ? app.$("officialRepoInput").value.trim() : "";
  const assetName = advanced ? app.$("packAssetInput").value.trim() : "";
  const ref = advanced ? app.optional("packRefInput")?.value.trim() || "" : "";
  return runPackAction(async () => {
    const result = await app.runQueuedJob("/api/packs/download/jobs", {
      method: "POST",
      body: JSON.stringify({
        repository: repository || null,
        asset_name: assetName || null,
        ref: ref || null,
      }),
      onQueued: onPackQueued,
    });
    verifyOfficialInstall(result, !advanced || !ref);
    return result;
  }, "검증된 공식 문제 팩을 설치하는 중...", officialPackErrorMessage);
}

async function installDefaultPack() {
  return downloadOfficialPack({ advanced: false });
}

async function retryPackInstall() {
  if (!retryPackAction) return;
  await retryPackAction();
}

function viewPackJob() {
  app.closeModals();
  app.openJobs(true);
}
/**
 * 문제팩 action state 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updatePackActionState() {
  const fileInput = app.optional("packFileInput");
  const busy = state.isBusy || state.pendingJobAction;
  app.setDisabled("uploadPackButton", busy || !fileInput?.files?.length);
  app.setDisabled("downloadPackButton", busy);
  app.setDisabled("defaultPackInstallButton", busy);
  app.setDisabled("packRetryButton", busy || !retryPackAction);
}

Object.assign(app, {
  downloadOfficialPack,
  installDefaultPack,
  installLabel,
  officialPackErrorMessage,
  renderPacks,
  renderPacksDisclosure,
  renderPackJobProgress,
  retryPackInstall,
  togglePacksDisclosure,
  updatePackActionState,
  uploadPack,
  viewPackJob,
});

app.optional("packSectionToggle")?.addEventListener("click", togglePacksDisclosure);
renderPacksDisclosure();
