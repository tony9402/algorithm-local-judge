/**
 * Git 화면 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { escapeHtml, optional, pathDisclosureHtml } from "./dom.js";
import { bindControlPolicy, renderControlPolicies } from "./control-policy.js";
import { trapFocusWithin } from "./modal.js";
import { state } from "./state.js";

const GIT_CONTROL_IDS = {
  gitFetchButton: "git.fetch",
  gitPullButton: "git.pull",
  gitCommitButton: "git.commit",
  gitPushButton: "git.push",
};
const COMPACT_GIT_QUERY = "(max-width: 1199px)";
const gitViewCallbacks = {
  closeJobCenter: () => {},
  closeSidebar: () => {},
};
let gitDrawerTrigger = null;

export function configureGitView(callbacks = {}) {
  Object.assign(gitViewCallbacks, callbacks);
}

export function compactGitDrawerActive() {
  return window.matchMedia?.(COMPACT_GIT_QUERY).matches ?? false;
}

export function isGitDrawerOpen() {
  return !optional("gitDrawer")?.classList.contains("hidden");
}

function setGitBackgroundInert(inert) {
  for (const id of ["sidebarToggle", "sidebarBackdrop", "alertStack"]) {
    optional(id)?.toggleAttribute("inert", inert);
  }
  document.querySelector(".shell")?.toggleAttribute("inert", inert);
}

export function syncGitDrawerAccessibility() {
  const drawer = optional("gitDrawer");
  const button = optional("gitDrawerButton");
  if (!drawer || !button) return;
  const open = isGitDrawerOpen();
  const compact = compactGitDrawerActive();
  drawer.setAttribute("role", compact ? "dialog" : "complementary");
  if (compact) drawer.setAttribute("aria-modal", "true");
  else drawer.removeAttribute("aria-modal");
  drawer.setAttribute("aria-hidden", open ? "false" : "true");
  drawer.toggleAttribute("tabindex", compact);
  button.setAttribute("aria-expanded", String(open));
  document.body.classList.toggle("git-drawer-open", open);
  document.body.classList.toggle("git-drawer-modal-open", open && compact);
  setGitBackgroundInert(open && compact);
}

export function openGitDrawer(trigger = document.activeElement) {
  const drawer = optional("gitDrawer");
  if (!drawer) return false;
  gitViewCallbacks.closeJobCenter({ restoreFocus: false });
  gitDrawerTrigger = trigger instanceof HTMLElement ? trigger : optional("gitDrawerButton");
  if (compactGitDrawerActive()) gitViewCallbacks.closeSidebar({ restoreFocus: false });
  drawer.classList.remove("hidden");
  syncGitDrawerAccessibility();
  window.requestAnimationFrame(() => optional("gitDrawerCloseButton")?.focus());
  return true;
}

export function closeGitDrawer(options = {}) {
  const drawer = optional("gitDrawer");
  if (!drawer || drawer.classList.contains("hidden")) {
    syncGitDrawerAccessibility();
    return false;
  }
  drawer.classList.add("hidden");
  syncGitDrawerAccessibility();
  if (options.restoreFocus !== false) {
    const fallback = optional("sidebarToggle");
    const triggerVisible = !compactGitDrawerActive()
      && gitDrawerTrigger?.isConnected
      && (gitDrawerTrigger.offsetParent || gitDrawerTrigger.getClientRects().length);
    (triggerVisible ? gitDrawerTrigger : fallback)?.focus();
  }
  gitDrawerTrigger = null;
  return true;
}

export function bindGitDrawer() {
  optional("gitDrawerButton")?.addEventListener("click", (event) => openGitDrawer(event.currentTarget));
  optional("gitDrawerCloseButton")?.addEventListener("click", () => closeGitDrawer());
  document.addEventListener("keydown", (event) => {
    if (!isGitDrawerOpen()) return;
    if (compactGitDrawerActive()) trapFocusWithin(event, optional("gitDrawer"));
  });
  window.matchMedia?.(COMPACT_GIT_QUERY).addEventListener("change", syncGitDrawerAccessibility);
  syncGitDrawerAccessibility();
}

function renderGitSummary(status) {
  const branch = optional("gitSummaryBranch");
  const changes = optional("gitSummaryChanges");
  if (!branch || !changes) return;
  if (!status?.isRepository) {
    branch.textContent = "사용 불가";
    changes.textContent = "Git 저장소 아님";
    return;
  }
  branch.textContent = status.branch || "분리된 HEAD";
  const count = status.files?.length || 0;
  changes.textContent = status.writeEnabled === false
    ? `변경 ${count} · 작업 차단`
    : count
      ? `변경 ${count}`
      : "변경 없음";
}

function bindGitControlPolicies() {
  for (const [controlId, policyKey] of Object.entries(GIT_CONTROL_IDS)) {
    bindControlPolicy(optional(controlId), policyKey, {
      reasonTarget: "gitControlReason",
      dependents: controlId === "gitCommitButton" ? [optional("gitCommitMessage")] : [],
    });
  }
  renderControlPolicies(Object.values(GIT_CONTROL_IDS));
}
/**
 * Git 상태 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.
 *
 * @param {Array} status Git 상태을 계산하거나 검증할 때 필요한 상태 입력입니다.
 */
export function renderGitStatus(status) {
  state.gitStatus = status;
  renderGitSummary(status);
  const panel = optional("gitStatus");
  if (!panel) return;
  if (!status?.isRepository) {
    panel.classList.add("muted");
    panel.innerHTML = `
      <div class="git-card empty">
        <div class="git-card-title">Git 저장소가 아닙니다.</div>
        <p>이 워크스페이스에서는 Git 동기화 작업을 사용할 수 없습니다.</p>
      </div>
    `;
    bindGitControlPolicies();
    return;
  }
  const fileCount = status.files?.length || 0;
  const remote = status.remote || "원격 저장소 없음";
  const upstream = status.upstream || "추적 브랜치 없음";
  const branch = status.branch || "분리된 HEAD";
  const repositoryName = status.repositoryName || "현재 워크스페이스";
  const repositoryPath = status.repositoryPath || status.workspace || "";
  const warnings = [];
  if (status.dirty) {
    warnings.push("저장소에 커밋되지 않은 변경이 있습니다. 제출 전 변경 파일을 확인하세요.");
  }
  if (!status.writeEnabled) {
    warnings.push(
      "현재 서버 연결 정책으로 Git 가져오기, 당겨오기, 커밋, 푸시가 차단됩니다."
    );
  }
  if (status.repositoryWarning?.message) {
    warnings.push(status.repositoryWarning.message);
  }
  if (!status.upstream) {
    warnings.push("추적 브랜치가 없습니다. 푸시 전에 원격 브랜치 연결 상태를 확인하세요.");
  }
  const badges = [
    status.dirty ? `변경 ${fileCount}개` : "변경 없음",
  ].filter(Boolean);
  panel.classList.remove("muted");
  panel.innerHTML = `
    <div class="git-card">
      <div class="git-card-topline">
        <span class="git-branch" title="${escapeHtml(repositoryName)}">${escapeHtml(repositoryName)}</span>
        <span class="git-head">${escapeHtml(status.head || "HEAD 없음")}</span>
      </div>
      <div class="git-badges">
        ${badges.map((badge) => `<span>${escapeHtml(badge)}</span>`).join("")}
      </div>
      <dl class="git-meta-grid">
        <div>
          <dt>브랜치</dt>
          <dd title="${escapeHtml(branch)}">${escapeHtml(branch)}</dd>
        </div>
        <div>
          <dt>추적</dt>
          <dd title="${escapeHtml(upstream)}">${escapeHtml(upstream)}</dd>
        </div>
        <div>
          <dt>동기화</dt>
          <dd>앞섬 ${status.ahead || 0} / 뒤처짐 ${status.behind || 0}</dd>
        </div>
        <div class="git-meta-wide">
          <dt>원격</dt>
          <dd>${pathDisclosureHtml(remote)}</dd>
        </div>
        <div class="git-meta-wide">
          <dt>위치</dt>
          <dd>${pathDisclosureHtml(repositoryPath)}</dd>
        </div>
      </dl>
    </div>
    ${
      warnings.length
        ? `<ul class="danger-note git-warning-list">${warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
        : ""
    }
  `;
  bindGitControlPolicies();
}
