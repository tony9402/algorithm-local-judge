import {
  LAST_RESULTS_KEY,
  activeRepositoryKey,
  state,
} from "./state.js";
import { readStorage, writeStorage } from "./storage.js";

export const LAST_RESULTS_STORAGE_KEY = LAST_RESULTS_KEY;

export function storedLastResults() {
  const results = readStorage(LAST_RESULTS_KEY);
  return results && typeof results === "object" ? results : {};
}

function resultKey(problemId = state.selectedProblem) {
  return problemId ? `${activeRepositoryKey()}:${problemId}` : null;
}

export function persistProblemLastResult(patch, problemId = state.selectedProblem) {
  const key = resultKey(problemId);
  if (!key) return;
  const results = storedLastResults();
  results[key] = {
    ...(results[key] || {}),
    ...patch,
    problemId,
    repositoryName: state.activeRepository || null,
    updatedAt: Date.now(),
  };
  writeStorage(LAST_RESULTS_KEY, results);
}

export function currentProblemResult(problemId = state.selectedProblem) {
  const key = resultKey(problemId);
  return key ? storedLastResults()[key] || null : null;
}

export function hasFreshFullTest(problemId = state.selectedProblem) {
  const result = currentProblemResult(problemId);
  return Boolean(result?.fullTest?.passed && !result?.dirtyAfterFullTest);
}

export function clearProblemLastResult(problemId = state.selectedProblem) {
  const key = resultKey(problemId);
  if (!key) return;
  const results = storedLastResults();
  if (!results[key]) return;
  delete results[key];
  writeStorage(LAST_RESULTS_KEY, results);
}

export function migrateProblemLastResult(previousProblemId, nextProblemId) {
  if (!previousProblemId || !nextProblemId || previousProblemId === nextProblemId) return;
  const results = storedLastResults();
  const previousKey = resultKey(previousProblemId);
  const nextKey = resultKey(nextProblemId);
  if (!previousKey || !nextKey || !results[previousKey]) return;
  results[nextKey] = {
    ...results[previousKey],
    problemId: nextProblemId,
    repositoryName: state.activeRepository || null,
    updatedAt: Date.now(),
  };
  delete results[previousKey];
  writeStorage(LAST_RESULTS_KEY, results);
}
