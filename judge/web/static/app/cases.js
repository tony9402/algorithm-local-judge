/**
 * 케이스 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
const { state } = app;

function formatCaseDiagnostic(diagnostic) {
  const line = diagnostic.line ? `:${diagnostic.line}` : "";
  const profile = diagnostic.profile ? `profile ${diagnostic.profile}, ` : "";
  const location = diagnostic.location || "cases.yml";
  const hint = diagnostic.hint ? `\n\nhint:\n  ${diagnostic.hint}` : "";
  return `${diagnostic.path}${line}\n  ${profile}${location}\n  ${diagnostic.message}${hint}`;
}

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
async function compileCasesData({ showSuccess = true, profile = app.judgeProfile() } = {}) {
  app.setStatusCard("cases", "Checking", `${profile} cases.yml`);
  const result = await app.runQueuedJob("/api/cases/jobs", {
    method: "POST",
    body: JSON.stringify({
      problem_id: app.$("problemSelect").value,
      profile,
    }),
  });
  if (showSuccess || !result.valid) {
    state.debugLogs = formatCasesCompile(result).split("\n");
    app.renderDebugLog();
    app.setBadge(result.valid ? "Cases OK" : "Cases Invalid", result.valid ? "accepted" : "wrong");
    if (result.valid) {
      const caseCount = compiledCaseCount(result);
      app.setStatusCard("cases", "OK", app.profileCaseText(caseCount, profile));
      app.setSummary(`${profile} cases.yml expanded successfully.`, "result-summary success");
    } else {
      const first = result.diagnostics[0];
      app.setStatusCard("cases", "Invalid", first?.location || "-");
      app.setSummary(first?.message || "cases.yml compile failed.", "result-summary error");
    }
  } else if (result.valid) {
    const caseCount = compiledCaseCount(result);
    app.setStatusCard("cases", "OK", app.profileCaseText(caseCount, profile));
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

function compiledCaseCount(result) {
  return result.profiles.reduce((total, profile) => total + (profile.caseCount || 0), 0);
}

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
