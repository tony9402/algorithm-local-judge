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
    return `cases.yml: 유효하지 않음\n\n${result.diagnostics.map(formatCaseDiagnostic).join("\n\n")}`;
  }
  const lines = ["cases.yml: 정상"];
  for (const profile of result.profiles) {
    lines.push(`profile ${profile.name}: ${profile.caseCount}개 케이스`);
  }
  return lines.join("\n");
}
async function compileCasesData({ showSuccess = true, profile = app.judgeProfile() } = {}) {
  app.setStatusCard("cases", "검사 중", `${profile} cases.yml`);
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
    app.setBadge(result.valid ? "Cases 정상" : "Cases 오류", result.valid ? "accepted" : "wrong");
    if (result.valid) {
      const caseCount = compiledCaseCount(result);
      app.setStatusCard("cases", "정상", app.profileCaseText(caseCount, profile));
      app.setSummary(`${profile} cases.yml 전개가 완료되었습니다.`, "result-summary success");
    } else {
      const first = result.diagnostics[0];
      app.setStatusCard("cases", "오류", first?.location || "-");
      app.setSummary(first?.message || "cases.yml 검사에 실패했습니다.", "result-summary error");
    }
  } else if (result.valid) {
    const caseCount = compiledCaseCount(result);
    app.setStatusCard("cases", "정상", app.profileCaseText(caseCount, profile));
  } else {
    const first = result.diagnostics[0];
    state.debugLogs = formatCasesCompile(result).split("\n");
    app.renderDebugLog();
    app.setBadge("Cases 오류", "wrong");
    app.setStatusCard("cases", "오류", first?.location || "-");
    app.setSummary(first?.message || "cases.yml 검사에 실패했습니다.", "result-summary error");
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
