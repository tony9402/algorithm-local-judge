const app = window.AljApp;
const { state } = app;

/**
 * formatCaseDiagnostic 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} diagnostic `diagnostic` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function formatCaseDiagnostic(diagnostic) {
  const line = diagnostic.line ? `:${diagnostic.line}` : "";
  const profile = diagnostic.profile ? `profile ${diagnostic.profile}, ` : "";
  const location = diagnostic.location || "cases.yml";
  const hint = diagnostic.hint ? `\n\nhint:\n  ${diagnostic.hint}` : "";
  return `${diagnostic.path}${line}\n  ${profile}${location}\n  ${diagnostic.message}${hint}`;
}

/**
 * formatCasesCompile 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} result `result` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function formatCasesCompile(result) {
  if (!result.valid) {
    return `cases.yml: invalid\n\n${result.diagnostics.map(formatCaseDiagnostic).join("\n\n")}`;
  }
  const lines = ["cases.yml: ok"];
  for (const profile of result.profiles) {
    lines.push(`profile ${profile.name}: ${profile.caseCount} case(s)`);
  }
  return lines.join("\n");
}

/**
 * compileCasesData 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} options `options` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function compileCasesData({ showSuccess = true } = {}) {
  app.setStatusCard("cases", "Checking", `${app.judgeProfile()} cases.yml`);
  const result = await app.runQueuedJob("/api/cases/jobs", {
    method: "POST",
    body: JSON.stringify({
      problem_id: app.$("problemSelect").value,
      profile: app.judgeProfile(),
    }),
  });
  if (showSuccess || !result.valid) {
    state.debugLogs = formatCasesCompile(result).split("\n");
    app.renderDebugLog();
    app.setBadge(result.valid ? "Cases OK" : "Cases Invalid", result.valid ? "accepted" : "wrong");
    if (result.valid) {
      const caseCount = compiledCaseCount(result);
      app.setStatusCard("cases", "OK", app.profileCaseText(caseCount));
      app.setSummary(`${app.judgeProfile()} cases.yml expanded successfully.`, "result-summary success");
    } else {
      const first = result.diagnostics[0];
      app.setStatusCard("cases", "Invalid", first?.location || "-");
      app.setSummary(first?.message || "cases.yml compile failed.", "result-summary error");
    }
  } else if (result.valid) {
    const caseCount = compiledCaseCount(result);
    app.setStatusCard("cases", "OK", app.profileCaseText(caseCount));
  } else {
    const first = result.diagnostics[0];
    state.debugLogs = formatCasesCompile(result).split("\n");
    app.renderDebugLog();
    app.setBadge("Cases Invalid", "wrong");
    app.setStatusCard("cases", "Invalid", first?.location || "-");
    app.setSummary(first?.message || "cases.yml compile failed.", "result-summary error");
  }
  return result;
}

/**
 * compiledCaseCount 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} result `result` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function compiledCaseCount(result) {
  return result.profiles.reduce((total, profile) => total + (profile.caseCount || 0), 0);
}

/**
 * compileCasesOnly 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
async function compileCasesOnly() {
  await compileCasesData({ showSuccess: true });
}

Object.assign(app, {
  compiledCaseCount,
  compileCasesData,
  compileCasesOnly,
  formatCaseDiagnostic,
  formatCasesCompile,
});
