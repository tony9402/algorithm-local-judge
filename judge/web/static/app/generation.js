/**
 * 생성 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
/**
 * generate 데이터 장시간 작업을 큐에 등록하고 UI가 추적할 작업 상태를 구성합니다.
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
