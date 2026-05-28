import { normalizeErrorDetail } from "./api.js";
import {
  STATUS_LABELS,
  state,
} from "./state.js";

/**
 * statusLabelForResult 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} status `status` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function statusLabelForResult(status) {
  return STATUS_LABELS[status] || status || "-";
}

/**
 * statusToneForResult 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} status `status` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function statusToneForResult(status) {
  if (status === "ok" || status === "accepted") return "ok";
  if (status === "time_limit" || status === "memory_limit") return "warn";
  return "bad";
}

/**
 * formatDurationMs 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function formatDurationMs(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  if (numeric >= 1000) return `${(numeric / 1000).toFixed(2)} s`;
  return `${Math.round(numeric)} ms`;
}

/**
 * formatMemoryBytes 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function formatMemoryBytes(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  if (numeric >= 1024 * 1024) return `${(numeric / 1024 / 1024).toFixed(1)} MB`;
  if (numeric >= 1024) return `${(numeric / 1024).toFixed(1)} KB`;
  return `${Math.round(numeric)} B`;
}

/**
 * solutionCheckCases 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} check `check` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function solutionCheckCases(check) {
  return Array.isArray(check?.cases) ? check.cases : [];
}

/**
 * solutionCaseName 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} item `item` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function solutionCaseName(item) {
  return item?.case || item?.caseId || item?.name || "-";
}

/**
 * solutionCaseStatus 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} item `item` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function solutionCaseStatus(item) {
  return item?.status || "unknown";
}

/**
 * solutionCaseTime 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} item `item` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function solutionCaseTime(item) {
  return item?.timeMs ?? item?.elapsedMs ?? item?.time ?? null;
}

/**
 * solutionCaseMemory 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} item `item` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function solutionCaseMemory(item) {
  return item?.memoryBytes ?? item?.memory ?? item?.memoryKb ?? null;
}

/**
 * maxMetricFromCases 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} cases `cases` 값입니다.
 * @param {any} getter `getter` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function maxMetricFromCases(cases, getter) {
  const values = cases
    .map(getter)
    .map((value) => (value === null || value === undefined ? NaN : Number(value)))
    .filter(Number.isFinite);
  return values.length ? Math.max(...values) : null;
}

/**
 * solutionCheckMetrics 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} check `check` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * solutionCheckSource 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} check `check` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function solutionCheckSource(check) {
  return check.source || check.path || check.file || "알 수 없는 솔루션";
}

/**
 * failedSolutionChecks 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} result `result` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function failedSolutionChecks(result) {
  return (result?.checks || []).filter((check) => !check.passed);
}

/**
 * normalizedSolutionPath 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function normalizedSolutionPath(value) {
  return String(value || "").replace(/^\.?\//, "");
}

/**
 * dirtySolutionSet 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function dirtySolutionSet() {
  return new Set((state.dirtySolutionPaths || []).map(normalizedSolutionPath));
}

/**
 * solutionCheckForPath 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function solutionCheckForPath(path) {
  const checks = state.lastSolutionVerification?.checks || [];
  const normalizedPath = normalizedSolutionPath(path);
  return checks.find((check) => {
    const source = normalizedSolutionPath(solutionCheckSource(check));
    return source === normalizedPath || source.endsWith(`/${normalizedPath}`);
  });
}

/**
 * solutionValidationStatusForFile 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function solutionValidationStatusForFile(path) {
  if (dirtySolutionSet().has(normalizedSolutionPath(path))) {
    return {
      className: "stale",
      label: "변경 후 재검증 필요",
      title: `${path} · 소스 변경 후 솔루션 테스트 필요`,
    };
  }
  if (!state.lastSolutionVerification) return null;
  const check = solutionCheckForPath(path);
  if (!check) return null;
  const expected = statusLabelForResult(check.expectedStatus);
  const actual = statusLabelForResult(check.actualStatus);
  if (check.passed) {
    return {
      className: "match",
      label: `기대 ${expected} · 일치`,
      title: `${path} · 기대 ${expected} · 일치`,
    };
  }
  const details = `기대 ${expected} · 실제 ${actual}`;
  return {
    className: "mismatch",
    label: details,
    title: `${path} · ${details}`,
  };
}

/**
 * formatSolutionFailureSummary 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} result `result` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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
