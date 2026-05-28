import {
  PROBLEM_TASK_LOCK_NAME,
  RUN_ALL_LOCK_KEY,
  RUN_ALL_LOCK_TTL_MS,
  TAB_INSTANCE_ID,
  runAllChannel,
  state,
} from "../state.js";
import { readStorage, removeStorage, writeStorage } from "../storage.js";

const RUN_ALL_LOCK_HEARTBEAT_MS = 2000;
const RUN_ALL_LOCK_ORPHAN_GRACE_MS = 10000;
const RUN_ALL_JOB_KINDS = new Set(["full-check", "workspace-pack-build"]);
const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "cancelling"]);
const runAllLeaseTimers = new Map();

export function currentRunAllLock() {
  const lock = readStorage(RUN_ALL_LOCK_KEY);
  if (!lock?.token || !lock?.expiresAt) return null;
  if (Number(lock.expiresAt) <= Date.now()) {
    removeStorage(RUN_ALL_LOCK_KEY);
    return null;
  }
  return lock;
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
    const stored = currentRunAllLock();
    if (stored?.token !== lock.token || stored.owner !== TAB_INSTANCE_ID) {
      stopRunAllLeaseTimer(lock.token);
      return;
    }
    writeStorage(RUN_ALL_LOCK_KEY, {
      ...stored,
      heartbeatAt: Date.now(),
      expiresAt: Date.now() + RUN_ALL_LOCK_TTL_MS,
    });
  }, RUN_ALL_LOCK_HEARTBEAT_MS);
  runAllLeaseTimers.set(lock.token, timer);
}

export function acquireRunAllLease(problemId = state.selectedProblem) {
  const existing = currentRunAllLock();
  if (existing && existing.owner !== TAB_INSTANCE_ID) return null;
  const now = Date.now();
  const lock = {
    owner: TAB_INSTANCE_ID,
    token: window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
    problemId,
    startedAt: now,
    heartbeatAt: now,
    expiresAt: now + RUN_ALL_LOCK_TTL_MS,
  };
  writeStorage(RUN_ALL_LOCK_KEY, lock);
  const stored = currentRunAllLock();
  if (!stored || stored.token !== lock.token) return null;
  startRunAllLeaseHeartbeat(lock);
  announceRunAllLock();
  return lock;
}

export function releaseRunAllLease(lock) {
  if (lock?.token) stopRunAllLeaseTimer(lock.token);
  const stored = currentRunAllLock();
  if (stored?.token === lock?.token) {
    removeStorage(RUN_ALL_LOCK_KEY);
    announceRunAllLock();
  }
}

export function reconcileRunAllLockWithJobs(jobs = []) {
  const lock = currentRunAllLock();
  if (!lock || lock.owner === TAB_INSTANCE_ID || hasActiveRunAllJob(jobs)) return false;
  const heartbeatAt = lockHeartbeatAt(lock);
  if (heartbeatAt && Date.now() - heartbeatAt < RUN_ALL_LOCK_ORPHAN_GRACE_MS) return false;
  removeStorage(RUN_ALL_LOCK_KEY);
  announceRunAllLock();
  return true;
}

export async function withProblemTaskLock(action) {
  if (!navigator.locks?.request) return action();
  return navigator.locks.request(PROBLEM_TASK_LOCK_NAME, { ifAvailable: true }, async (lock) => {
    if (!lock) throw new Error("이미 다른 탭에서 전체 테스트 또는 팩 빌드가 실행 중입니다.");
    return action();
  });
}
