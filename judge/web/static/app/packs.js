const app = window.AljApp;
const { state } = app;

function installLabel(result) {
  const target = result.assetName || result.label || result.installedPath || "installed problems";
  if (result.installType === "source") {
    return `Installed source fallback: ${target}`;
  }
  const security = result.checksumVerified ? " · checksum verified" : "";
  return `Installed pack: ${target}${security}`;
}

function officialPackErrorMessage(error) {
  const detail = String(error?.message || "unknown error");
  const lower = detail.toLowerCase();
  if (error?.status === 403 || lower.includes("rate limit")) {
    return `Official pack install failed: GitHub rate limit or permission blocked the request. Try again later, choose a specific ref, or install a downloaded .aljpack. Detail: ${detail}`;
  }
  if (error?.status === 404 || lower.includes("not found")) {
    return `Official pack install failed: repository, ref, or release asset was not found. Check the repository, branch/tag, and asset name. Detail: ${detail}`;
  }
  if (lower.includes("untrusted repository")) {
    return `Official pack install failed: repository is not trusted. Add it with judge pack trust add owner/name, or use the default trusted repository. Detail: ${detail}`;
  }
  if (lower.includes("checksum")) {
    return `Official pack install failed: release checksum verification failed. Ask the publisher to upload a matching .sha256 file. Detail: ${detail}`;
  }
  if (lower.includes("aljpack") || lower.includes("asset")) {
    return `Official pack install failed: no matching .aljpack asset was available for this platform. Choose an asset name or use source fallback only for trusted repositories. Detail: ${detail}`;
  }
  if (lower.includes("platform")) {
    return `Official pack install failed: the selected pack does not match this platform. Choose a pack built for this OS/CPU. Detail: ${detail}`;
  }
  return `Official pack install failed: ${detail}`;
}

function renderPacks(packs) {
  const list = app.$("packList");
  list.innerHTML = "";
  if (!packs.length) {
    list.textContent = "No problem packs installed.";
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

async function uploadPack() {
  const file = app.$("packFileInput").files[0];
  if (!file) throw new Error("Problem pack file is required.");
  app.$("packStatus").textContent = "Installing uploaded pack...";
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

async function downloadOfficialPack() {
  const repository = app.$("officialRepoInput").value.trim();
  const assetName = app.$("packAssetInput").value.trim();
  const ref = app.optional("packRefInput")?.value.trim() || "";
  app.$("packStatus").textContent = "Installing official problems...";
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
