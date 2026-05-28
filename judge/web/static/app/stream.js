/**
 * 스트림 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

const app = window.AljApp;

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
