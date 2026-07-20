/**
 * 생성 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
/**
 * generate 데이터 장시간 작업을 큐에 등록하고 UI가 추적할 작업 상태를 구성합니다.
 */
async function generateData() {
  app.clearDebugLog();
  app.setBadge("생성 중", "neutral");
  app.setStatusCard("data", "대기 중", app.profileLabel(app.judgeProfile()));
  app.setStatusCard("judge", "대기");
  app.setStatusCard("run", "-", "채점 기록 없음");
  app.setSummary(`${app.profileLabel(app.judgeProfile())} 테스트 데이터를 준비하는 중입니다.`, "result-summary");
  const compileResult = await app.compileCasesData({ showSuccess: false });
  if (!compileResult.valid) return;
  const totalCases = app.compiledCaseCount(compileResult);
  app.setGenerationProgress(0, totalCases, "데이터 생성");
  app.setStatusCard("data", "생성 중", `0 / ${app.profileCaseText(totalCases)}`);
  const result = await app.runQueuedJob("/api/generate/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      problem_id: app.$("problemSelect").value,
      profile: app.judgeProfile(),
      force: app.$("forceGenerateInput").checked,
    }),
  });
  app.setGenerationProgress(result.caseCount, result.caseCount, "데이터 생성");
  app.setStatusCard("data", "생성 완료", app.profileCaseText(result.caseCount, result.profile));
  app.setSummary(`${app.profileLabel(result.profile)} 테스트 데이터 준비 완료: ${result.label}`, "result-summary success");
  app.setBadge("생성 완료", "accepted");
}

Object.assign(app, {
  generateData,
});
