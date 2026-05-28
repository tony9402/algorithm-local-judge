import { escapeHtml, optional } from "./dom.js";
import { state } from "./state.js";

export function renderGitStatus(status) {
  state.gitStatus = status;
  const panel = optional("gitStatus");
  if (!panel) return;
  const setDisabled = (button, disabled, reason = "") => {
    if (!button) return;
    button.disabled = disabled;
    button.toggleAttribute("disabled", disabled);
    if (reason && disabled) {
      button.title = reason;
      button.setAttribute("aria-label", `${button.textContent || "Git action"}: ${reason}`);
    } else {
      button.removeAttribute("title");
      button.removeAttribute("aria-label");
    }
  };
  const buttons = [
    optional("gitFetchButton"),
    optional("gitPullButton"),
    optional("gitCommitButton"),
    optional("gitPushButton"),
  ].filter(Boolean);
  if (!status?.isRepository) {
    panel.classList.add("muted");
    panel.innerHTML = `
      <div class="git-card empty">
        <div class="git-card-title">Git repository가 아닙니다.</div>
        <p>이 워크스페이스에서는 Git 동기화 작업을 사용할 수 없습니다.</p>
      </div>
    `;
    for (const button of buttons) setDisabled(button, true, "Git repository가 아닙니다.");
    window.setTimeout(() => {
      for (const button of [
        optional("gitFetchButton"),
        optional("gitPullButton"),
        optional("gitCommitButton"),
        optional("gitPushButton"),
      ]) {
        setDisabled(button, true, "Git repository가 아닙니다.");
      }
    }, 0);
    return;
  }
  const fileCount = status.files?.length || 0;
  const remote = status.remote || "remote 없음";
  const upstream = status.upstream || "upstream 없음";
  const branch = status.branch || "detached";
  const repositoryName = status.repositoryName || "현재 워크스페이스";
  const repositoryPath = status.repositoryPath || status.workspace || "";
  const warnings = [];
  if (status.dirty) {
    warnings.push("저장소에 커밋되지 않은 변경이 있습니다. 제출 전 변경 파일을 확인하세요.");
  }
  if (!status.writeEnabled) {
    warnings.push(
      "Git network/write actions are disabled for this server binding. fetch, pull, commit, push가 차단됩니다."
    );
  }
  if (status.repositoryWarning?.message) {
    warnings.push(status.repositoryWarning.message);
  }
  if (!status.upstream) {
    warnings.push("upstream이 없습니다. push 전 원격 branch 연결 상태를 확인하세요.");
  }
  const badges = [
    status.dirty ? `${fileCount} changed` : "clean",
  ].filter(Boolean);
  panel.classList.remove("muted");
  panel.innerHTML = `
    <div class="git-card">
      <div class="git-card-topline">
        <span class="git-branch" title="${escapeHtml(repositoryName)}">${escapeHtml(repositoryName)}</span>
        <span class="git-head">${escapeHtml(status.head || "no HEAD")}</span>
      </div>
      <div class="git-badges">
        ${badges.map((badge) => `<span>${escapeHtml(badge)}</span>`).join("")}
      </div>
      <dl class="git-meta-grid">
        <div>
          <dt>branch</dt>
          <dd title="${escapeHtml(branch)}">${escapeHtml(branch)}</dd>
        </div>
        <div>
          <dt>upstream</dt>
          <dd title="${escapeHtml(upstream)}">${escapeHtml(upstream)}</dd>
        </div>
        <div>
          <dt>sync</dt>
          <dd>ahead ${status.ahead || 0} / behind ${status.behind || 0}</dd>
        </div>
        <div class="git-meta-wide">
          <dt>remote</dt>
          <dd title="${escapeHtml(remote)}">${escapeHtml(remote)}</dd>
        </div>
        <div class="git-meta-wide">
          <dt>path</dt>
          <dd title="${escapeHtml(repositoryPath)}">${escapeHtml(repositoryPath)}</dd>
        </div>
      </dl>
    </div>
    ${
      warnings.length
        ? `<ul class="danger-note git-warning-list">${warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
        : ""
    }
  `;
  const applyButtonPolicy = () => {
    const fetchButton = optional("gitFetchButton");
    const pullButton = optional("gitPullButton");
    const commitButton = optional("gitCommitButton");
    const pushButton = optional("gitPushButton");
    const wrongRepository = Boolean(status.toolRepositoryRemote);
    const writeReason = !status.writeEnabled
      ? "서버 정책으로 Git 쓰기/네트워크 작업이 차단되었습니다."
      : wrongRepository
        ? "문제 저장소가 아니라 도구 저장소 remote라서 차단되었습니다."
        : "";
    setDisabled(fetchButton, !status.writeEnabled || wrongRepository, writeReason);
    setDisabled(pullButton, !status.writeEnabled || wrongRepository, writeReason);
    setDisabled(
      commitButton,
      !status.writeEnabled || wrongRepository || !fileCount,
      writeReason || (!fileCount ? "커밋할 변경 파일이 없습니다." : "")
    );
    setDisabled(
      pushButton,
      !status.writeEnabled
        || wrongRepository
        || Number(status.behind || 0) > 0,
      writeReason
        || (Number(status.behind || 0) > 0 ? "원격보다 뒤처져 있어 먼저 pull이 필요합니다." : "")
    );
  };
  applyButtonPolicy();
  window.setTimeout(applyButtonPolicy, 0);
}
