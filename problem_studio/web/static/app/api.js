export function normalizeErrorDetail(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map(normalizeErrorDetail).filter(Boolean).join("\n");
  }
  if (typeof detail === "object") {
    const location = Array.isArray(detail.loc) ? detail.loc.join(".") : detail.loc;
    const message = detail.msg || detail.message || detail.detail;
    if (location && message) return `${location}: ${message}`;
    if (message) return normalizeErrorDetail(message);
    return Object.entries(detail)
      .map(([key, value]) => `${key}: ${normalizeErrorDetail(value) || String(value)}`)
      .join(", ");
  }
  return String(detail);
}

export async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = isFormData
    ? { ...(options.headers || {}) }
    : { "Content-Type": "application/json", ...(options.headers || {}) };
  const response = await fetch(path, { headers, ...options });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail = typeof body === "object" && body.detail ? body.detail : body;
    const error = new Error(normalizeErrorDetail(detail) || `HTTP ${response.status}`);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}
