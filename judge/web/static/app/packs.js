/**
 * 문제팩 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;

function installLabel(result) {
  const target = result.assetName || result.label || result.installedPath || "설치된 문제";
  if (result.installType === "source") {
    return `소스 fallback 설치 완료: ${target}`;
  }
  const security = result.checksumVerified ? " · 체크섬 확인됨" : "";
  return `문제 팩 설치 완료: ${target}${security}`;
}

function officialPackErrorMessage(error) {
  const detail = String(error?.message || "unknown error");
  const lower = detail.toLowerCase();
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
  if (lower.includes("aljpack") || lower.includes("asset")) {
    return `공식 문제 설치 실패: 현재 플랫폼에 맞는 .aljpack asset이 없습니다. asset 이름을 지정하거나 신뢰한 저장소에서만 source fallback을 사용하세요. 상세: ${detail}`;
  }
  if (lower.includes("platform")) {
    return `공식 문제 설치 실패: 선택한 팩이 현재 플랫폼과 맞지 않습니다. 이 OS/CPU용 팩을 선택하세요. 상세: ${detail}`;
  }
  return `공식 문제 설치 실패: ${detail}`;
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
    return;
  }
  list.classList.remove("muted");
  for (const pack of packs) {
    const item = document.createElement("div");
    item.className = "list-item";
    const platforms = (pack.supportedPlatforms || []).join(", ");
    const problems = (pack.problems || []).join(", ");
    const packLabel = `${app.escapeHtml(pack.packId)} ${app.escapeHtml(pack.version || "")}`;
    item.innerHTML = `<strong>${packLabel}</strong><span>${app.escapeHtml(platforms)} · ${app.escapeHtml(problems)}</span>`;
    list.appendChild(item);
  }
}
/**
 * 업로드 문제팩 장시간 작업을 큐에 등록하고 UI가 추적할 작업 상태를 구성합니다.
 */
async function uploadPack() {
  const file = app.$("packFileInput").files[0];
  if (!file) throw new Error("문제 팩 파일이 필요합니다.");
  app.$("packStatus").textContent = "업로드한 문제 팩을 설치하는 중...";
  app.$("packStatus").className = "modal-status";
  const formData = new FormData();
  formData.append("file", file);
  const result = await app.runQueuedJob("/api/packs/upload/jobs", {
    method: "POST",
    body: formData,
  });
  app.$("packStatus").textContent = installLabel(result);
  app.$("packStatus").className = "modal-status success";
  app.clearSampleCache();
  await app.refresh();
}
/**
 * 다운로드 official 문제팩 장시간 작업을 큐에 등록하고 UI가 추적할 작업 상태를 구성합니다.
 */
async function downloadOfficialPack() {
  const repository = app.$("officialRepoInput").value.trim();
  const assetName = app.$("packAssetInput").value.trim();
  const ref = app.optional("packRefInput")?.value.trim() || "";
  app.$("packStatus").textContent = "공식 문제 팩을 설치하는 중...";
  app.$("packStatus").className = "modal-status";
  let result;
  try {
    result = await app.runQueuedJob("/api/packs/download/jobs", {
      method: "POST",
      body: JSON.stringify({
        repository: repository || null,
        asset_name: assetName || null,
        ref: ref || null,
      }),
    });
  } catch (error) {
    const message = officialPackErrorMessage(error);
    app.$("packStatus").textContent = message;
    app.$("packStatus").className = "modal-status error";
    throw new Error(message);
  }
  app.$("packStatus").textContent = installLabel(result);
  app.$("packStatus").className = "modal-status success";
  app.clearSampleCache();
  await app.refresh();
}
/**
 * 문제팩 action state 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.
 */
function updatePackActionState() {
  const fileInput = app.optional("packFileInput");
  app.setDisabled("uploadPackButton", state.isBusy || !fileInput?.files?.length);
  app.setDisabled("downloadPackButton", state.isBusy);
}

Object.assign(app, {
  downloadOfficialPack,
  installLabel,
  officialPackErrorMessage,
  renderPacks,
  updatePackActionState,
  uploadPack,
});
