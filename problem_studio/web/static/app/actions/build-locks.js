/**
 * build locks 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import {
  PROBLEM_TASK_LOCK_NAME,
  RUN_ALL_LOCK_KEY,
  RUN_ALL_LOCK_TTL_MS,
  TAB_INSTANCE_ID,
  activeRepositoryKey,
  problemStateKey,
  runAllChannel,
  state,
} from "../state.js";
import { readStorage, removeStorage, writeStorage } from "../storage.js";

const RUN_ALL_LOCK_HEARTBEAT_MS = 2000;
const RUN_ALL_LOCK_ORPHAN_GRACE_MS = 10000;
const RUN_ALL_JOB_KINDS = new Set(["full-check", "workspace-pack-build"]);
const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "cancelling"]);
const runAllLeaseTimers = new Map();

function lockProblemKey(problemId = state.selectedProblem, repositoryName = state.activeRepository || null) {
  return problemStateKey(problemId, repositoryName);
}

function readRunAllLockMap() {
  const stored = readStorage(RUN_ALL_LOCK_KEY);
  if (!stored || typeof stored !== "object") return {};
  if (stored.locksByProblem && typeof stored.locksByProblem === "object") {
    return stored.locksByProblem;
  }
  if (stored.token && stored.problemId) {
    return {
      [lockProblemKey(stored.problemId, stored.repositoryName || null)]: stored,
    };
  }
  return {};
}

function writeRunAllLockMap(locks) {
  const keys = Object.keys(locks || {});
  if (!keys.length) {
    removeStorage(RUN_ALL_LOCK_KEY);
    return;
  }
  writeStorage(RUN_ALL_LOCK_KEY, {
    locksByProblem: locks,
    updatedAt: Date.now(),
  });
}

function writeRunAllLock(lock) {
  const locks = readRunAllLockMap();
  locks[lockProblemKey(lock.problemId, lock.repositoryName || null)] = lock;
  writeRunAllLockMap(locks);
}

function removeRunAllLock(lock) {
  const locks = readRunAllLockMap();
  delete locks[lockProblemKey(lock.problemId, lock.repositoryName || null)];
  writeRunAllLockMap(locks);
}

function normalizeCurrentLock(lock, key, locks) {
  if (!lock?.token || !lock?.expiresAt) {
    delete locks[key];
    return null;
  }
  if (Number(lock.expiresAt) <= Date.now()) {
    delete locks[key];
    writeRunAllLockMap(locks);
    return null;
  }
  return lock;
}

export function currentRunAllLock(
  problemId = state.selectedProblem,
  repositoryName = state.activeRepository || null
) {
  const locks = readRunAllLockMap();
  const key = lockProblemKey(problemId, repositoryName);
  return normalizeCurrentLock(locks[key], key, locks);
}

export function allRunAllLocks(repositoryName = state.activeRepository || null) {
  const locks = readRunAllLockMap();
  const active = [];
  let changed = false;
  for (const [key, lock] of Object.entries(locks)) {
    const current = normalizeCurrentLock(lock, key, locks);
    if (!current) {
      changed = true;
      continue;
    }
    if ((current.repositoryName || null) === (repositoryName || null)) active.push(current);
  }
  if (changed) writeRunAllLockMap(locks);
  return active;
}

function lockHeartbeatAt(lock) {
  return Number(lock?.heartbeatAt || lock?.startedAt || 0);
}

function hasActiveRunAllJob(jobs = []) {
  return jobs.some((job) => RUN_ALL_JOB_KINDS.has(job.kind) && ACTIVE_JOB_STATUSES.has(job.status));
}
export function announceRunAllLock() {
  runAllChannel?.postMessage({ type: "run-all-lock-changed" });
}

function stopRunAllLeaseTimer(token) {
  const timer = runAllLeaseTimers.get(token);
  if (timer) window.clearInterval(timer);
  runAllLeaseTimers.delete(token);
}

function startRunAllLeaseHeartbeat(lock) {
  stopRunAllLeaseTimer(lock.token);
  const timer = window.setInterval(() => {
    const stored = currentRunAllLock(lock.problemId, lock.repositoryName || null);
    if (stored?.token !== lock.token || stored.owner !== TAB_INSTANCE_ID) {
      stopRunAllLeaseTimer(lock.token);
      return;
    }
    writeRunAllLock({
      ...stored,
      heartbeatAt: Date.now(),
      expiresAt: Date.now() + RUN_ALL_LOCK_TTL_MS,
    });
  }, RUN_ALL_LOCK_HEARTBEAT_MS);
  runAllLeaseTimers.set(lock.token, timer);
}
export function acquireRunAllLease(problemId = state.selectedProblem) {
  const repositoryName = state.activeRepository || null;
  const existing = currentRunAllLock(problemId, repositoryName);
  if (existing && existing.owner !== TAB_INSTANCE_ID) return null;
  const now = Date.now();
  const lock = {
    owner: TAB_INSTANCE_ID,
    token: window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
    problemId,
    repositoryName,
    startedAt: now,
    heartbeatAt: now,
    expiresAt: now + RUN_ALL_LOCK_TTL_MS,
  };
  writeRunAllLock(lock);
  const stored = currentRunAllLock(problemId, repositoryName);
  if (!stored || stored.token !== lock.token) return null;
  startRunAllLeaseHeartbeat(lock);
  announceRunAllLock();
  return lock;
}
export function releaseRunAllLease(lock) {
  if (lock?.token) stopRunAllLeaseTimer(lock.token);
  const stored = currentRunAllLock(lock?.problemId, lock?.repositoryName || null);
  if (stored?.token === lock?.token) {
    removeRunAllLock(lock);
    announceRunAllLock();
  }
}
export function reconcileRunAllLockWithJobs(jobs = []) {
  if (hasActiveRunAllJob(jobs)) return false;
  const locks = readRunAllLockMap();
  let changed = false;
  for (const [key, lock] of Object.entries(locks)) {
    const current = normalizeCurrentLock(lock, key, locks);
    if (!current || current.owner === TAB_INSTANCE_ID) {
      changed = changed || !current;
      continue;
    }
    const heartbeatAt = lockHeartbeatAt(current);
    if (heartbeatAt && Date.now() - heartbeatAt < RUN_ALL_LOCK_ORPHAN_GRACE_MS) continue;
    delete locks[key];
    changed = true;
  }
  if (!changed) return false;
  writeRunAllLockMap(locks);
  announceRunAllLock();
  return true;
}
export async function withProblemTaskLock(action, problemId = state.selectedProblem) {
  if (!navigator.locks?.request) return action();
  const lockName = `${PROBLEM_TASK_LOCK_NAME}:${activeRepositoryKey()}:${problemId || "workspace"}`;
  return navigator.locks.request(lockName, { ifAvailable: true }, async (lock) => {
    if (!lock) throw new Error("이미 다른 탭에서 전체 테스트 또는 팩 빌드가 실행 중입니다.");
    return action();
  });
}
