const app = window.AljApp;

/**
 * generateData 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
async function generateData() {
  app.clearDebugLog();
  app.setBadge("Generating", "neutral");
  app.setStatusCard("data", "Waiting", app.judgeProfile());
  app.setStatusCard("judge", "Idle");
  app.setStatusCard("run", "-", "No run");
  app.setSummary(`Preparing ${app.judgeProfile()} test data.`, "result-summary");
  const compileResult = await app.compileCasesData({ showSuccess: false });
  if (!compileResult.valid) return;
  const totalCases = app.compiledCaseCount(compileResult);
  app.setGenerationProgress(0, totalCases, "Data generation");
  app.setStatusCard("data", "Generating", `0 / ${app.profileCaseText(totalCases)}`);
  const result = await app.runQueuedJob("/api/generate/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      problem_id: app.$("problemSelect").value,
      profile: app.judgeProfile(),
      force: app.$("forceGenerateInput").checked,
    }),
  });
  app.setGenerationProgress(result.caseCount, result.caseCount, "Data generation");
  app.setStatusCard("data", "Generated", app.profileCaseText(result.caseCount, result.profile));
  app.setSummary(`${result.profile} test data ready: ${result.label}`, "result-summary success");
  app.setBadge("Generated", "accepted");
}

Object.assign(app, {
  generateData,
});
