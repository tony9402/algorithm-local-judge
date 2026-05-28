import { normalizeErrorDetail } from "./api.js";
import { optional } from "./dom.js";

/**
 * alertTypeFromClass 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} className `className` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function alertTypeFromClass(className = "") {
  if (className.includes("error")) return "error";
  if (className.includes("success")) return "success";
  if (className.includes("warning")) return "warning";
  return "info";
}

/**
 * alertTitle 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} type `type` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function alertTitle(type) {
  if (type === "success") return "완료";
  if (type === "warning") return "주의";
  if (type === "error") return "오류";
  return "알림";
}

/**
 * showAlert 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @param {any} type `type` 값입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function showAlert(message, type = "info", options = {}) {
  const stack = optional("alertStack");
  if (!stack) {
    window.alert(message);
    return;
  }
  const existing = stack.querySelectorAll(".app-alert");
  for (const item of Array.from(existing).slice(0, Math.max(0, existing.length - 3))) {
    item.remove();
  }
  const alert = document.createElement("section");
  alert.className = `app-alert ${type}`;
  alert.setAttribute("role", "alert");

  const body = document.createElement("div");
  body.className = "alert-body";

  const title = document.createElement("strong");
  title.textContent = options.title || alertTitle(type);

  const content = document.createElement("p");
  content.textContent = normalizeErrorDetail(message) || "알 수 없는 문제가 발생했습니다.";

  const close = document.createElement("button");
  close.className = "alert-close";
  close.type = "button";
  close.setAttribute("aria-label", "알림 닫기");
  close.textContent = "×";
  close.addEventListener("click", () => alert.remove());

  body.append(title, content);
  alert.append(body, close);
  stack.appendChild(alert);

  const timeout = options.timeout ?? (type === "error" ? 8000 : 4200);
  if (timeout > 0) {
    window.setTimeout(() => alert.remove(), timeout);
  }
}

/**
 * showResult 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @param {any} className `className` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function showResult(message, className = "") {
  const type = alertTypeFromClass(className);
  showAlert(message, type, { title: alertTitle(type) });
}

/**
 * appendOutput 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} message 메시지입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function appendOutput(message) {
  void message;
}

/**
 * clearOutput 함수를 실행하고 반환 값을 계산합니다.
 *
 * @returns {any} 처리 결과를 반환합니다.
 */
export function clearOutput() {
  // Kept for command flows that previously reset command output state.
}

/**
 * errorKindForDetail 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} detail `detail` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function errorKindForDetail(detail) {
  const normalized = normalizeErrorDetail(detail);
  const text = normalized.toLowerCase();
  /**
   * includesAny 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} tokens `tokens` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  const includesAny = (...tokens) => tokens.some((token) => text.includes(token));
  if (includesAny("timed out", "timeout")) {
    return {
      label: "시간 초과",
      hint: "제한 시간, 무한 루프, 입력 크기와 생성/검증 로직의 복잡도를 확인하세요.",
    };
  }
  if (includesAny("required tool not found", "install one of")) {
    return {
      label: "환경 설정 오류",
      hint: "로컬에 필요한 컴파일러나 런타임이 설치되어 있고 PATH 또는 환경 변수가 맞는지 확인하세요.",
    };
  }
  if (includesAny("cases.yml compile failed", "cases.yml: invalid", "unknown variable")) {
    return {
      label: "cases.yml 설정 오류",
      hint: "cases.yml의 profile, repeat/matrix, 변수명, 들여쓰기와 line 정보를 먼저 확인하세요.",
    };
  }
  if (includesAny("compile error", "compile failed", "java compile failed", "compiler output")) {
    return {
      label: "컴파일 오류",
      hint: "대상 소스의 문법, include/import, 타입, 컴파일 로그 경로와 compiler output을 확인하세요.",
    };
  }
  if (includesAny("validator failed", "expected eof", "expected eoln", "not in range", "violates")) {
    return {
      label: "데이터 검증 실패",
      hint: "generator가 만든 입력과 validator가 읽는 값의 개수, 줄바꿈, 제약 조건이 맞는지 확인하세요.",
    };
  }
  if (includesAny("checker self-check failed")) {
    return {
      label: "체커 검증 실패",
      hint: "checker가 정답 출력과 동일한 출력도 허용하는지, checker 인자 처리와 stderr를 확인하세요.",
    };
  }
  if (includesAny("solution expectation check failed")) {
    return {
      label: "솔루션 기대 결과 불일치",
      hint: "기대 결과가 파일명과 맞는지, 실제 판정과 메시지를 솔루션 탭의 실패 항목에서 확인하세요.",
    };
  }
  if (includesAny("solution failed")) {
    return {
      label: "기준 정답 런타임 오류",
      hint: "기준 정답이 생성된 입력에서 예외 종료했는지, stderr와 입력 preview를 확인하세요.",
    };
  }
  if (includesAny("generator failed for case", "generator runtime error", "exit code")) {
    return {
      label: "Generator 런타임 오류",
      hint: "실패한 case의 seed/args와 generator.cpp의 예외 종료, stderr를 확인하세요.",
    };
  }
  if (includesAny("generator script failed", "generator script produced no cases")) {
    return {
      label: "데이터 생성 오류",
      hint: "cases.yml에서 선택된 profile과 generator 출력 파일 생성 여부를 확인하세요.",
    };
  }
  if (includesAny("pack build")) {
    return {
      label: "팩 빌드 오류",
      hint: "전체 테스트 통과 상태, 출력 폴더, pack 설정과 백그라운드 작업 로그를 확인하세요.",
    };
  }
  return {
    label: "실행 오류",
    hint: "실패 단계와 원문 상세를 기준으로 관련 파일을 확인하세요.",
  };
}

/**
 * formatOperationFailure 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} detail `detail` 값입니다.
 * @param {any} rows `rows` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function formatOperationFailure(detail, rows = []) {
  const normalized = normalizeErrorDetail(detail) || "알 수 없는 문제가 발생했습니다.";
  const kind = errorKindForDetail(normalized);
  return [
    `오류 유형: ${kind.label}`,
    kind.hint ? `확인 포인트: ${kind.hint}` : "",
    ...rows.filter(Boolean),
    "에러 상세",
    normalized,
  ].filter(Boolean).join("\n");
}
