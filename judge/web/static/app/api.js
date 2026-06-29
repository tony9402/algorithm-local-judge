/**
 * API 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;
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
    const message = typeof detail === "object" ? detail.message || JSON.stringify(detail) : detail;
    const error = new Error(message || `HTTP ${response.status}`);
    error.status = response.status;
    error.body = body;
    error.detail = detail;
    throw error;
  }
  return body;
}
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
    const message = typeof detail === "object" ? detail.message || JSON.stringify(detail) : detail;
    const error = new Error(message || `HTTP ${response.status}`);
    error.status = response.status;
    error.body = body;
    error.detail = detail;
    throw error;
  }
  return response;
}

Object.assign(app, {
  api,
  apiResponse,
});
