/**
 * 편집기와 제출 코드 뷰어가 공유하는 안전한 구문 강조 어댑터입니다.
 */

const app = window.AljApp;
const HIGHLIGHT_MAX_BYTES = 200 * 1024;
const HIGHLIGHT_MAX_LINES = 10000;
const HIGHLIGHT_CACHE_LIMIT = 24;
const HIGHLIGHT_LANGUAGE_LABELS = {
  cpp: "C++",
  java: "Java",
  plain: "일반 텍스트",
  python: "Python",
};
const highlightCache = new Map();
let highlightFrame = null;

function updateEditorLineNumbers() {
  const input = app.optional("sourceTextInput");
  const gutter = app.optional("sourceLineNumbers");
  if (!input || !gutter) return;
  const lineCount = Math.max(1, input.value.split("\n").length);
  const numbers = [];
  for (let index = 1; index <= lineCount; index += 1) {
    numbers.push(String(index));
  }
  gutter.textContent = numbers.join("\n");
}

function escapeHtml(value) {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function normalizeHighlightLanguage(language) {
  const key = String(language || "").trim().toLowerCase();
  if (key === "cpp" || key === "c++") return "cpp";
  if (key === "python" || key === "pypy") return "python";
  if (key === "java") return "java";
  return "plain";
}

function highlightLanguageLabel(language) {
  const key = String(language || "").trim().toLowerCase();
  if (key === "cpp" || key === "c++") return HIGHLIGHT_LANGUAGE_LABELS.cpp;
  if (key === "python") return HIGHLIGHT_LANGUAGE_LABELS.python;
  if (key === "pypy") return "PyPy";
  if (key === "java") return HIGHLIGHT_LANGUAGE_LABELS.java;
  return HIGHLIGHT_LANGUAGE_LABELS.plain;
}

function highlightSkipReason(source) {
  if (source.length > HIGHLIGHT_MAX_BYTES) return "bytes";
  let lines = 1;
  for (let index = 0; index < source.length; index += 1) {
    if (source.charCodeAt(index) === 10) {
      lines += 1;
      if (lines > HIGHLIGHT_MAX_LINES) return "lines";
    }
  }
  if (new TextEncoder().encode(source).byteLength > HIGHLIGHT_MAX_BYTES) return "bytes";
  return null;
}

function cacheHighlight(key, value) {
  if (highlightCache.has(key)) highlightCache.delete(key);
  highlightCache.set(key, value);
  while (highlightCache.size > HIGHLIGHT_CACHE_LIMIT) {
    highlightCache.delete(highlightCache.keys().next().value);
  }
  return value;
}

function highlightSourceCode(source, language) {
  const text = typeof source === "string" ? source : String(source ?? "");
  const normalizedLanguage = normalizeHighlightLanguage(language);
  const languageLabel = highlightLanguageLabel(language);
  const skipReason = highlightSkipReason(text);
  if (skipReason) {
    return {
      html: escapeHtml(text),
      language: "plain",
      languageLabel,
      skippedReason: skipReason,
    };
  }
  const cacheKey = `${normalizedLanguage}\u0000${languageLabel}\u0000${text}`;
  const cached = highlightCache.get(cacheKey);
  if (cached) {
    highlightCache.delete(cacheKey);
    highlightCache.set(cacheKey, cached);
    return cached;
  }

  // Prism normalizes non-breaking spaces; plain text preserves the submitted source byte-for-byte.
  if (normalizedLanguage === "plain" || text.includes("\u00a0")) {
    return cacheHighlight(cacheKey, {
      html: escapeHtml(text),
      language: "plain",
      languageLabel,
      skippedReason: null,
    });
  }

  try {
    const prism = window.Prism;
    const grammar = prism?.languages?.[normalizedLanguage];
    if (!grammar) throw new Error("Prism grammar is unavailable");
    return cacheHighlight(cacheKey, {
      html: prism.highlight(text, grammar, normalizedLanguage),
      language: normalizedLanguage,
      languageLabel,
      skippedReason: null,
    });
  } catch (_error) {
    return cacheHighlight(cacheKey, {
      html: escapeHtml(text),
      language: "plain",
      languageLabel,
      skippedReason: null,
    });
  }
}

function highlightCode(source, language) {
  return highlightSourceCode(source, language).html;
}

function renderCodeHighlight() {
  highlightFrame = null;
  const input = app.optional("sourceTextInput");
  const highlight = app.optional("sourceHighlight");
  if (!input || !highlight) return;
  const result = highlightSourceCode(input.value, app.$("editorLanguageLabel").textContent);
  highlight.className = `code-highlight language-${result.language}`;
  highlight.title = result.skippedReason ? "큰 소스이므로 구문 강조를 생략했습니다" : "";
  highlight.innerHTML = /* highlightSourceCode( returns escaped/tokenized markup */ result.html;
}

function updateCodeHighlight() {
  if (highlightFrame !== null) window.cancelAnimationFrame(highlightFrame);
  if (typeof window.requestAnimationFrame !== "function") {
    renderCodeHighlight();
    return;
  }
  highlightFrame = window.requestAnimationFrame(renderCodeHighlight);
}

function updateEditorView() {
  updateEditorLineNumbers();
  updateCodeHighlight();
}

function syncEditorScroll() {
  const input = app.optional("sourceTextInput");
  const gutter = app.optional("sourceLineNumbers");
  const highlight = app.optional("sourceHighlight");
  if (!input || !gutter) return;
  gutter.scrollTop = input.scrollTop;
  if (highlight) {
    highlight.scrollTop = input.scrollTop;
    highlight.scrollLeft = input.scrollLeft;
  }
}

function insertEditorText(text) {
  const input = app.$("sourceTextInput");
  const start = input.selectionStart;
  const end = input.selectionEnd;
  input.value = `${input.value.slice(0, start)}${text}${input.value.slice(end)}`;
  input.selectionStart = start + text.length;
  input.selectionEnd = start + text.length;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

Object.assign(app, {
  highlightCode,
  highlightLanguageLabel,
  highlightSourceCode,
  insertEditorText,
  normalizeHighlightLanguage,
  syncEditorScroll,
  updateCodeHighlight,
  updateEditorLineNumbers,
  updateEditorView,
});
