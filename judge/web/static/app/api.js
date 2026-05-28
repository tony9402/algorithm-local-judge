const app = window.AljApp;

/**
 * api 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    headers: isFormData
      ? { ...(options.headers || {}) }
      : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof body === "object" && body.detail ? body.detail : body;
    const error = new Error(detail || `HTTP ${response.status}`);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}

/**
 * apiResponse 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function apiResponse(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    headers: isFormData
      ? { ...(options.headers || {}) }
      : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok && response.status !== 304) {
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    const detail = typeof body === "object" && body.detail ? body.detail : body;
    const error = new Error(detail || `HTTP ${response.status}`);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return response;
}

Object.assign(app, {
  api,
  apiResponse,
});
