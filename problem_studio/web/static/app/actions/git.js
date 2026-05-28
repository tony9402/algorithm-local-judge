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
