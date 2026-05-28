/**
 * Git 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { api } from "../api.js";
import { optional } from "../dom.js";
import { renderGitStatus } from "../git-view.js?v=20260522-01";
import { saveOpenFileIfDirty } from "./files.js";

const gitCallbacks = {
  refresh: async () => {},
  renderProblems: () => {},
  renderWorkspace: () => {},
};
export function configureGitActions(callbacks = {}) {
  Object.assign(gitCallbacks, callbacks);
}
/**
 * Git 상태 데이터를 서버나 캐시에서 다시 읽어 화면 상태를 최신으로 맞춥니다.
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
export async function commitGitChanges() {
  const message = optional("gitCommitMessage")?.value.trim() || "";
  if (!message) throw new Error("commit message is required.");
  await saveOpenFileIfDirty();
  await runGitAction("commit", { message });
  const input = optional("gitCommitMessage");
  if (input) input.value = "";
  await gitCallbacks.refresh();
}
