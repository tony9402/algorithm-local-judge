const app = window.AljApp;

/**
 * parseSseBlock 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} block `block` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function parseSseBlock(block) {
  const lines = block.split("\n");
  let event = "message";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  const data = dataLines.length ? JSON.parse(dataLines.join("\n")) : {};
  return { event, data };
}

/**
 * streamRequest 비동기 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @param {any} options 옵션 모음입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
async function streamRequest(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop();
    for (const block of blocks) {
      if (!block.trim()) continue;
      const { event, data } = parseSseBlock(block);
      if (event === "log") {
        app.appendRunLog(data.message);
      } else if (event === "result") {
        finalResult = data;
      } else if (event === "error") {
        throw new Error(data.message);
      }
    }
  }
  return finalResult;
}

Object.assign(app, {
  parseSseBlock,
  streamRequest,
});
