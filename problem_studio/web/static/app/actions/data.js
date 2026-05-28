import { api, normalizeErrorDetail } from "../api.js";
import { setText } from "../dom.js";
import {
  appendOutput,
  clearOutput,
  formatOperationFailure,
  showAlert,
  showResult,
} from "../feedback.js";
import {
  beginProgress,
  setProgressInsight,
  setProgressStep,
  showLastRun,
  updateRunningProgressDetail,
} from "../progress.js";
import { parseSseBlock, streamProgressDetail } from "../sse.js";
import { state } from "../state.js";
import { runQueuedJob } from "../jobs-view.js";

const CASES_EXAMPLE_PREVIEW = [
  "profiles:",
  "  sample:",
  "    cases:",
  "      - name: sample-1",
  "        type: fixed",
  "        content: |",
  "          1",
  "  hidden:",
  "    cases:",
  "      - name: generated-1",
  "        type: generate",
  "        seed: 1",
].join("\n");

/**
 * showCasesAlertDetails 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} result `result` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function showCasesAlertDetails(result) {
  if (result.valid) return;
  /**
   * detail 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} result `result` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  const detail = (result.diagnostics || [])
    .map((item) => {
      const location = [item.profile, item.location, item.line ? `line ${item.line}` : ""]
        .filter(Boolean)
        .join(" / ");
      return location ? `${location}: ${item.message}` : item.message;
    })
    .join("; ");
  showAlert(
    `cases.yml 검사 실패: ${detail || "확인할 항목이 있습니다."} · 예제 preview와 line/location을 확인하세요.`,
    "error",
    { timeout: 10000 }
  );
}

/**
 * formatCasesDiagnostics 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} result `result` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function formatCasesDiagnostics(result) {
  const diagnostics = result.diagnostics || [];
  if (!diagnostics.length) return "cases.yml을 확인하세요.";
  return diagnostics
    .map((item) => {
      const location = [
        item.path || "generator/cases.yml",
        item.line ? `line ${item.line}` : "",
        item.profile ? `profile ${item.profile}` : "",
        item.location ? `location ${item.location}` : "",
      ].filter(Boolean).join(" · ");
      return [
        location,
        item.message ? `message: ${item.message}` : "",
        "expected: profile은 mapping, cases는 list, 각 case는 name/type을 포함",
        item.location ? `received location: ${item.location}` : "",
        item.hint ? `hint: ${item.hint}` : "",
      ].filter(Boolean).join("\n");
    })
    .join("\n\n")
    + `\n\n예제 preview:\n${CASES_EXAMPLE_PREVIEW}`;
}

/**
 * compileCases 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function compileCases(options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  if (options.clear !== false) clearOutput();
  const result = await runQueuedJob(
    `/api/problems/${state.selectedProblem}/cases/jobs`,
    { profile: null },
    { label: "Cases 검사" }
  );
  appendOutput(JSON.stringify(result, null, 2));
  showCasesAlertDetails(result);
  showLastRun(
    result.valid ? "Cases 검사 완료" : "Cases 검사 실패",
    result.valid
      ? `${result.profiles?.length || 0}개 profile을 확인했습니다.`
      : formatOperationFailure(
        `cases.yml compile failed\n\n${formatCasesDiagnostics(result)}`,
        ["대상: generator/cases.yml"]
      ),
    result.valid ? "success" : "error"
  );
  showResult(
    result.valid ? "cases.yml OK" : "cases.yml에 문제가 있습니다.",
    result.valid ? "summary success" : "summary error"
  );
  return result;
}

/**
 * compileTool 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} tool `tool` 값입니다.
 * @param {any} label `label` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function compileTool(tool, label, options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  if (options.clear !== false) clearOutput();
  const ownsProgress = !state.progress.active;
  if (ownsProgress) {
    beginProgress(`${label} 컴파일`, [{ label: `${label} 컴파일`, status: "running" }]);
    setProgressInsight(`${label} 컴파일`, `${label} 소스코드를 컴파일하고 있습니다.`);
  }
  try {
    const result = await runQueuedJob(
      `/api/problems/${state.selectedProblem}/tools/compile/jobs`,
      { tool },
      { label: `${label} 컴파일` }
    );
    appendOutput(JSON.stringify(result.labels || {}, null, 2));
    if (ownsProgress) setProgressStep(0, "success", `${label} 컴파일 완료`);
    showLastRun(`${label} 컴파일 완료`, `${label} 도구를 사용할 준비가 되었습니다.`, "success");
    showResult(`${label} compiled.`, "summary success");
    return result;
  } catch (error) {
    const detail = normalizeErrorDetail(error.message);
    if (ownsProgress) setProgressStep(0, "error", detail);
    showLastRun(
      `${label} 컴파일 실패`,
      formatOperationFailure(detail, [
        `대상: ${tool}`,
        state.lastStreamDetail ? `마지막 단계: ${state.lastStreamDetail}` : "",
      ]),
      "error"
    );
    throw error;
  }
}

/**
 * compileTools 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function compileTools(options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  if (options.clear !== false) clearOutput();
  const ownsProgress = !state.progress.active;
  if (ownsProgress) {
    beginProgress("전체 도구 컴파일", [{ label: "전체 도구 컴파일", status: "running" }]);
    setProgressInsight("전체 도구 컴파일", "generator, validator, checker와 기준 정답을 컴파일합니다.");
  }
  try {
    const result = await runQueuedJob(
      `/api/problems/${state.selectedProblem}/tools/compile/jobs`,
      {},
      { label: "전체 도구 컴파일" }
    );
    appendOutput(JSON.stringify(result.labels || {}, null, 2));
    const count = Object.keys(result.labels || {}).length;
    if (ownsProgress) setProgressStep(0, "success", `${count}개 도구 컴파일`);
    showLastRun(
      "전체 도구 컴파일 완료",
      `${count}개 도구를 사용할 준비가 되었습니다.`,
      "success"
    );
    showResult("Tools compiled.", "summary success");
    return result;
  } catch (error) {
    const detail = normalizeErrorDetail(error.message);
    if (ownsProgress) setProgressStep(0, "error", detail);
    showLastRun(
      "전체 도구 컴파일 실패",
      formatOperationFailure(detail, [
        "대상: generator, validator, checker, 기준 정답",
      ]),
      "error"
    );
    throw error;
  }
}

/**
 * streamRequest 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @param {any} body `body` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function streamRequest(path, body, options = {}) {
  if (options.clear !== false) clearOutput();
  state.lastStreamDetail = "";
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const errorBody = await response.json();
    throw new Error(normalizeErrorDetail(errorBody.detail || errorBody) || `HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop();
    for (const block of blocks) {
      if (!block.trim()) continue;
      const { event, data } = parseSseBlock(block);
      if (event === "log") {
        const detail = streamProgressDetail(data.message);
        state.lastStreamDetail = detail || data.message || "";
        setText("loadingTitle", options.progressTitle || "작업 진행 중");
        setText("loadingMessage", detail);
        if (state.progress.active) {
          setProgressInsight(options.progressTitle || "현재 작업", detail);
          if (!options.manualProgress) updateRunningProgressDetail(detail);
        }
        options.onLog?.(data.message, detail, data);
      }
      if (event === "result") finalResult = data;
      if (event === "error") throw new Error(normalizeErrorDetail(data.message));
    }
  }
  return finalResult;
}

/**
 * generateData 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} profile `profile` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function generateData(profile = "hidden", options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  const ownsProgress = !state.progress.active;
  if (ownsProgress) {
    beginProgress(`${profile} 데이터 생성`, [{ label: `${profile} 데이터 생성+검증`, status: "running" }]);
  }
  try {
    const result = await runQueuedJob(
      `/api/problems/${state.selectedProblem}/generate/jobs`,
      { profile, force: false },
      { ...options, label: `${profile} 데이터 생성+검증` }
    );
    appendOutput(JSON.stringify(result, null, 2));
    if (ownsProgress) setProgressStep(0, "success", `${result.caseCount}개 데이터 생성 및 검증`);
    showLastRun(
      `${profile} 데이터 생성 완료`,
      `${result.caseCount}개 ${profile} case를 생성하고 검증했습니다.`,
      "success"
    );
    showResult(`Generated ${result.caseCount} ${profile} case(s).`, "summary success");
    return result;
  } catch (error) {
    const detail = normalizeErrorDetail(error.message);
    if (ownsProgress) setProgressStep(0, "error", detail);
    showLastRun(
      `${profile} 데이터 생성 실패`,
      formatOperationFailure(detail, [
        `Profile: ${profile}`,
        state.lastStreamDetail ? `마지막 단계: ${state.lastStreamDetail}` : "",
        "관련 대상: generator/cases.yml, generator/generator.cpp, validator/validator.cpp",
      ]),
      "error"
    );
    throw error;
  }
}

/**
 * validateAllData 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export async function validateAllData(options = {}) {
  if (!state.selectedProblem) throw new Error("Select a problem first.");
  const ownsProgress = !state.progress.active;
  if (ownsProgress) {
    beginProgress("모든 데이터 생성+검증", [{ label: "모든 데이터 생성+검증", status: "running" }]);
  }
  try {
    const result = await runQueuedJob(
      `/api/problems/${state.selectedProblem}/validate/jobs`,
      { force: options.force === true },
      { ...options, label: "모든 데이터 생성+검증" }
    );
    appendOutput(JSON.stringify(result, null, 2));
    const profileCount = result.profileCount || 0;
    const caseCount = result.caseCount || 0;
    if (ownsProgress) setProgressStep(0, "success", `${profileCount}개 profile · ${caseCount}개 데이터 검증`);
    showLastRun(
      "모든 데이터 생성+검증 완료",
      `${profileCount}개 profile의 ${caseCount}개 데이터를 생성하고 검증했습니다.`,
      "success"
    );
    showResult(`Validated ${caseCount} case(s).`, "summary success");
    return result;
  } catch (error) {
    const detail = normalizeErrorDetail(error.message);
    if (ownsProgress) setProgressStep(0, "error", detail);
    showLastRun(
      "모든 데이터 생성+검증 실패",
      formatOperationFailure(detail, [
        state.lastStreamDetail ? `마지막 단계: ${state.lastStreamDetail}` : "",
        "관련 대상: generator/cases.yml, generator/generator.cpp, validator/validator.cpp",
      ]),
      "error"
    );
    throw error;
  }
}
