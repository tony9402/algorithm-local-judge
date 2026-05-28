import { api } from "../api.js";
import { optional } from "../dom.js";
import { renderGitStatus } from "../git-view.js?v=20260522-01";
import { saveOpenFileIfDirty } from "./files.js";

const gitCallbacks = {
  /**
   * refresh 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  refresh: async () => {},
  /**
   * renderProblems 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renderProblems: () => {},
  /**
   * renderWorkspace 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  renderWorkspace: () => {},
};

/**
 * configureGitActions 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} callbacks `callbacks` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function configureGitActions(callbacks = {}) {
  Object.assign(gitCallbacks, callbacks);
}

/**
 * refreshGitStatus 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function refreshGitStatus() {
  try {
    renderGitStatus(await api("/api/workspace/git/status"));
  } catch (error) {
    const panel = optional("gitStatus");
    if (panel) {
      panel.classList.add("muted");
      panel.textContent = error.message;
    }
  }
}

/**
 * runGitAction 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} action `action` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function runGitAction(action, options = {}) {
  const result = await api(`/api/workspace/git/${action}`, {
    method: "POST",
    body: JSON.stringify(options),
  });
  renderGitStatus(result.git || result);
  if (result.workspace) {
    gitCallbacks.renderWorkspace(result.workspace);
    gitCallbacks.renderProblems(result.workspace.problems || []);
  }
  if (action === "push" || action === "pull") {
    await gitCallbacks.refresh();
  }
  return result;
}

/**
 * commitGitChanges 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function commitGitChanges() {
  const message = optional("gitCommitMessage")?.value.trim() || "";
  if (!message) throw new Error("commit message is required.");
  await saveOpenFileIfDirty();
  await runGitAction("commit", { message });
  const input = optional("gitCommitMessage");
  if (input) input.value = "";
  await gitCallbacks.refresh();
}
