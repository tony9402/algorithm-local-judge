/**
 * highlight 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
 */

import { escapeHtml } from "../dom.js";
export function languageForPath(path) {
  const lower = (path || "").toLowerCase();
  if (lower.endsWith(".cpp") || lower.endsWith(".cc") || lower.endsWith(".cxx")) return "cpp";
  if (lower.endsWith(".py")) return "python";
  if (lower.endsWith(".java")) return "java";
  if (lower.endsWith(".yml") || lower.endsWith(".yaml")) return "yaml";
  if (lower.endsWith(".json")) return "json";
  return "text";
}

function protectMatches(value, patterns) {
  const placeholders = [];
  let highlighted = value;
  const mark = (content, className) => {
    const token = String.fromCodePoint(0xe000 + placeholders.length);
    placeholders.push({ token, html: `<span class="${className}">${content}</span>` });
    return token;
  };
  for (const { pattern, className, replacer } of patterns) {
    highlighted = highlighted.replace(pattern, (...args) => {
      if (replacer) return replacer(mark, ...args);
      return mark(args[0], className);
    });
  }
  return {
    value: highlighted,
    restore: (text) =>
      placeholders.reduce(
        (output, placeholder) => output.replaceAll(placeholder.token, placeholder.html),
        text
      ),
  };
}
export function highlightCode(text, language) {
  const escaped = escapeHtml(text || "");
  if (language === "json") {
    const protectedJson = protectMatches(escaped, [
      {
        pattern: /(&quot;[^&]*?&quot;)(\s*:)/g,
        replacer: (mark, _match, key, colon) => `${mark(key, "tok-key")}${colon}`,
      },
      { pattern: /(&quot;.*?&quot;)/g, className: "tok-string" },
    ]);
    return protectedJson.restore(
      protectedJson.value
        .replace(/\b(true|false|null)\b/g, '<span class="tok-keyword">$1</span>')
        .replace(/\b(-?\d+(?:\.\d+)?)\b/g, '<span class="tok-number">$1</span>')
    );
  }
  if (language === "yaml") {
    const protectedYaml = protectMatches(escaped, [
      { pattern: /^(\s*#.*)$/gm, className: "tok-comment" },
      { pattern: /(&quot;.*?&quot;)/g, className: "tok-string" },
    ]);
    return protectedYaml.restore(
      protectedYaml.value
        .replace(/^(\s*[-]?\s*[A-Za-z0-9_-]+)(:)/gm, '<span class="tok-key">$1</span>$2')
        .replace(/\b(-?\d+)\b/g, '<span class="tok-number">$1</span>')
    );
  }
  if (language === "python") {
    const protectedPython = protectMatches(escaped, [
      { pattern: /^(\s*#.*)$/gm, className: "tok-comment" },
      { pattern: /(&quot;.*?&quot;|'.*?')/g, className: "tok-string" },
    ]);
    return protectedPython.restore(
      protectedPython.value
        .replace(
          /\b(def|class|if|elif|else|for|while|return|import|from|as|try|except|with|pass|in|and|or|not|None|True|False)\b/g,
          '<span class="tok-keyword">$1</span>'
        )
        .replace(/\b(-?\d+)\b/g, '<span class="tok-number">$1</span>')
    );
  }
  if (language === "java" || language === "cpp") {
    const protectedCode = protectMatches(escaped, [
      { pattern: /(\/\/.*)$/gm, className: "tok-comment" },
      { pattern: /(&quot;.*?&quot;|'.*?')/g, className: "tok-string" },
    ]);
    return protectedCode.restore(
      protectedCode.value
        .replace(
          /\b(class|public|private|protected|static|void|int|long|double|float|char|bool|boolean|string|String|return|if|else|for|while|do|switch|case|break|continue|include|using|namespace|std|auto|const|vector|map|set)\b/g,
          '<span class="tok-keyword">$1</span>'
        )
        .replace(/\b(-?\d+)\b/g, '<span class="tok-number">$1</span>')
    );
  }
  return escaped;
}
export function codeMirrorModeForPath(path) {
  const language = languageForPath(path);
  return codeMirrorModeForLanguage(language);
}
export function codeMirrorModeForLanguage(language) {
  return {
    cpp: "text/x-c++src",
    java: "text/x-java",
    python: "python",
    json: "application/json",
    yaml: "yaml",
    text: "text/plain",
  }[language] || "text/plain";
}
export function normalizeCodeMirrorVimMode(mode) {
  const value = String(mode || "").toLowerCase();
  if (value.includes("insert")) return "insert";
  if (value.includes("visual block")) return "visual-block";
  if (value.includes("visual line")) return "visual-line";
  if (value.includes("visual")) return "visual";
  return "normal";
}
