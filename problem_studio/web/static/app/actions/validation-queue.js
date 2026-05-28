import { showAlert } from "../feedback.js";
import { setProgressInsight } from "../progress.js";

export const VALIDATION_QUEUE_ACTIONS = new Set([
  "compileCases",
  "compileGenerator",
  "generateSample",
  "generateHidden",
  "compileValidator",
  "validateSample",
  "compileChecker",
  "compileReference",
  "compileTools",
  "verifySolutions",
  "runAllChecks",
  "buildPack",
]);

let queuedCount = 0;

/**
 * queuedValidationCount 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function queuedValidationCount() {
  return queuedCount;
}

/**
 * enqueueValidationAction 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} label `label` 값입니다.
 * @param {any} action `action` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function enqueueValidationAction(label, action) {
  queuedCount += 1;
  showAlert(`${label} 작업을 작업 센터에 보냅니다. 다른 편집 작업은 계속할 수 있습니다.`, "info", {
    title: "작업 센터",
    timeout: 4500,
  });

  /**
   * run 비동기 함수를 실행하고 반환 값을 계산합니다.
   *
   * @returns {any} 처리 결과를 반환합니다.
   */
  const run = async () => {
    setProgressInsight(
      "작업 센터",
      `${label} 작업을 server-side queue에서 실행합니다. 화면은 잠그지 않습니다.`
    );
    try {
      return await action();
    } finally {
      queuedCount = Math.max(0, queuedCount - 1);
    }
  };
  return run();
}
