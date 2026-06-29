/**
 * 솔루션 상태 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { normalizeErrorDetail } from "./api.js";
import {
  STATUS_LABELS,
  state,
} from "./state.js";
export function statusLabelForResult(status) {
  return STATUS_LABELS[status] || status || "-";
}
export function statusToneForResult(status) {
  if (status === "ok" || status === "accepted") return "ok";
  if (status === "time_limit" || status === "memory_limit") return "warn";
  return "bad";
}
export function formatDurationMs(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  if (numeric >= 1000) return `${(numeric / 1000).toFixed(2)} s`;
  return `${Math.round(numeric)} ms`;
}
export function formatMemoryBytes(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  if (numeric >= 1024 * 1024) return `${(numeric / 1024 / 1024).toFixed(1)} MB`;
  if (numeric >= 1024) return `${(numeric / 1024).toFixed(1)} KB`;
  return `${Math.round(numeric)} B`;
}
export function solutionCheckCases(check) {
  return Array.isArray(check?.cases) ? check.cases : [];
}
export function solutionCaseName(item) {
  return item?.case || item?.caseId || item?.name || "-";
}
export function solutionCaseStatus(item) {
  return item?.status || "unknown";
}
export function solutionCaseTime(item) {
  return item?.timeMs ?? item?.elapsedMs ?? item?.time ?? null;
}
export function solutionCaseMemory(item) {
  return item?.memoryBytes ?? item?.memory ?? item?.memoryKb ?? null;
}
export function maxMetricFromCases(cases, getter) {
  const values = cases
    .map(getter)
    .map((value) => (value === null || value === undefined ? NaN : Number(value)))
    .filter(Number.isFinite);
  return values.length ? Math.max(...values) : null;
}
export function solutionCheckMetrics(check) {
  const cases = solutionCheckCases(check);
  const metrics = check?.metrics || {};
  const maxTimeMs = metrics.maxTimeMs ?? maxMetricFromCases(cases, solutionCaseTime);
  const maxMemoryBytes = metrics.maxMemoryBytes ?? maxMetricFromCases(cases, solutionCaseMemory);
  const okCases = cases.filter((item) => solutionCaseStatus(item) === "ok").length;
  return {
    totalCases: cases.length,
    okCases,
    maxTimeMs,
    maxMemoryBytes,
  };
}
export function solutionCheckSource(check) {
  return check.source || check.path || check.file || "알 수 없는 솔루션";
}
export function failedSolutionChecks(result) {
  return (result?.checks || []).filter((check) => !check.passed);
}
export function normalizedSolutionPath(value) {
  return String(value || "").replace(/^\.?\//, "");
}
export function dirtySolutionSet() {
  return new Set((state.dirtySolutionPaths || []).map(normalizedSolutionPath));
}
function activeStatus(value) {
  return ["queued", "running", "cancelling", "verifying", "testing"].includes(value);
}
export function isFullSolutionVerificationActive(problemId = state.selectedProblem) {
  const active = state.activeSolutionVerification;
  return Boolean(
    active
      && active.problemId === problemId
      && (active.repositoryName || null) === (state.activeRepository || null)
      && activeStatus(active.status)
  );
}
export function isSolutionTestActive(path, problemId = state.selectedProblem) {
  const active = state.activeSolutionTestsByPath?.[normalizedSolutionPath(path)];
  return Boolean(
    active
      && active.problemId === problemId
      && (active.repositoryName || null) === (state.activeRepository || null)
      && activeStatus(active.status)
  );
}
function checkMatchesPath(check, normalizedPath) {
  const source = normalizedSolutionPath(solutionCheckSource(check));
  return source === normalizedPath || source.endsWith(`/${normalizedPath}`);
}
export function fullSolutionCheckForPath(path) {
  const normalizedPath = normalizedSolutionPath(path);
  return (state.lastSolutionVerification?.checks || []).find((check) =>
    checkMatchesPath(check, normalizedPath)
  );
}
export function solutionTestCheckForPath(path) {
  if (isFullSolutionVerificationActive() || isSolutionTestActive(path)) return null;
  const normalizedPath = normalizedSolutionPath(path);
  const result = state.solutionTestResultsByPath?.[normalizedPath];
  return (result?.checks || []).find((check) => checkMatchesPath(check, normalizedPath));
}
export function solutionCheckForPath(path) {
  if (dirtySolutionSet().has(normalizedSolutionPath(path))) {
    return solutionTestCheckForPath(path) || fullSolutionCheckForPath(path);
  }
  return fullSolutionCheckForPath(path) || solutionTestCheckForPath(path);
}
export function solutionValidationStatusForFile(path) {
  const fullCheck = fullSolutionCheckForPath(path);
  if (isFullSolutionVerificationActive()) {
    if (fullCheck) {
      const expected = statusLabelForResult(fullCheck.expectedStatus);
      const actual = statusLabelForResult(fullCheck.actualStatus);
      if (fullCheck.passed) {
        return {
          className: "match",
          label: `검증 중 · 기대 ${expected} 일치`,
          title: `${path} · 전체 검증 중 완료 · 기대 ${expected} · 일치`,
        };
      }
      return {
        className: "mismatch",
        label: `검증 중 · 기대 ${expected} · 실제 ${actual}`,
        title: `${path} · 전체 검증 중 완료 · 기대 ${expected} · 실제 ${actual}`,
      };
    }
    return {
      className: "verifying",
      label: "검증중",
      title: `${path} · 기대 결과 전체 검증 중`,
    };
  }
  if (isSolutionTestActive(path)) {
    return {
      className: "test-running",
      label: "개별 테스트 중",
      title: `${path} · 개별 테스트 실행 중`,
    };
  }
  const dirty = dirtySolutionSet().has(normalizedSolutionPath(path));
  const testCheck = solutionTestCheckForPath(path);
  if (dirty && testCheck) {
    const expected = statusLabelForResult(testCheck.expectedStatus);
    const actual = statusLabelForResult(testCheck.actualStatus);
    return {
      className: "stale",
      label: `개별 테스트 ${actual} · 전체 재검증 필요`,
      title: `${path} · 개별 테스트 기대 ${expected} · 실제 ${actual} · 전체 기대 결과 검증 필요`,
    };
  }
  if (dirty) {
    return {
      className: "stale",
      label: "변경 후 재검증 필요",
      title: `${path} · 소스 변경 후 솔루션 테스트 필요`,
    };
  }
  const visibleTestCheck = fullCheck ? null : testCheck;
  const check = fullCheck || visibleTestCheck;
  if (!check) return null;
  const expected = statusLabelForResult(check.expectedStatus);
  const actual = statusLabelForResult(check.actualStatus);
  if (check.passed) {
    return {
      className: "match",
      label: fullCheck ? `기대 ${expected} · 일치` : `개별 테스트 ${expected} · 일치`,
      title: fullCheck
        ? `${path} · 기대 ${expected} · 일치`
        : `${path} · 개별 테스트 · 기대 ${expected} · 일치`,
    };
  }
  const details = `기대 ${expected} · 실제 ${actual}`;
  return {
    className: "mismatch",
    label: fullCheck ? details : `개별 테스트 · ${details}`,
    title: fullCheck ? `${path} · ${details}` : `${path} · 개별 테스트 · ${details}`,
  };
}
export function formatSolutionFailureSummary(result, options = {}) {
  const failed = failedSolutionChecks(result);
  if (!failed.length) return "솔루션 기대 결과와 다른 항목이 있습니다.";
  const limit = options.limit ?? 8;
  const shown = failed.slice(0, limit);
  const lines = [
    `${result.profile || "hidden"} profile에서 기대 결과와 다른 솔루션 ${failed.length}개`,
  ];
  for (const check of shown) {
    lines.push(
      `- ${solutionCheckSource(check)}`,
      `  기대: ${statusLabelForResult(check.expectedStatus)} · 실제: ${statusLabelForResult(check.actualStatus)}`
    );
    if (check.runId) lines.push(`  run: ${check.runId}`);
    if (check.message) {
      const message = normalizeErrorDetail(check.message);
      if (message) lines.push(`  ${message}`);
    }
  }
  if (failed.length > shown.length) {
    lines.push(`- 외 ${failed.length - shown.length}개 솔루션은 솔루션 탭에서 확인하세요.`);
  }
  return lines.join("\n");
}
