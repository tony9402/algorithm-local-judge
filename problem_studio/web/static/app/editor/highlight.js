import { escapeHtml } from "../dom.js";

/**
 * languageForPath 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function languageForPath(path) {
  /**
   * lower 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} path 경로 문자열입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
  const lower = (path || "").toLowerCase();
  if (lower.endsWith(".cpp") || lower.endsWith(".cc") || lower.endsWith(".cxx")) return "cpp";
  if (lower.endsWith(".py")) return "python";
  if (lower.endsWith(".java")) return "java";
  if (lower.endsWith(".yml") || lower.endsWith(".yaml")) return "yaml";
  if (lower.endsWith(".json")) return "json";
  return "text";
}

/**
 * protectMatches 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} patterns `patterns` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
function protectMatches(value, patterns) {
  const placeholders = [];
  let highlighted = value;
  /**
   * mark 함수를 실행하고 반환 값을 계산합니다.
   *
   * @param {any} content 요청/저장할 내용입니다.
   * @param {any} className `className` 값입니다.
   * @returns {any} 처리 결과를 반환합니다.
   */
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
    /**
     * restore 함수를 실행하고 반환 값을 계산합니다.
     *
     * @param {any} text `text` 값입니다.
     * @returns {any} 처리 결과를 반환합니다.
     */
    restore: (text) =>
      placeholders.reduce(
        (output, placeholder) => output.replaceAll(placeholder.token, placeholder.html),
        text
      ),
  };
}

/**
 * highlightCode 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} text `text` 값입니다.
 * @param {any} language `language` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function highlightCode(text, language) {
  const escaped = escapeHtml(text || "");
  if (language === "json") {
    const protectedJson = protectMatches(escaped, [
      {
        pattern: /(&quot;[^&]*?&quot;)(\s*:)/g,
        /**
         * replacer 함수를 실행하고 반환 값을 계산합니다.
         *
         * @param {any} mark `mark` 값입니다.
         * @param {any} _match `_match` 값입니다.
         * @param {any} key `key` 값입니다.
         * @param {any} colon `colon` 값입니다.
         * @returns {any} 처리 결과를 반환합니다.
         */
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

/**
 * codeMirrorModeForPath 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} path 경로 문자열입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function codeMirrorModeForPath(path) {
  const language = languageForPath(path);
  return codeMirrorModeForLanguage(language);
}

/**
 * codeMirrorModeForLanguage 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} language `language` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
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

/**
 * normalizeCodeMirrorVimMode 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} mode `mode` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function normalizeCodeMirrorVimMode(mode) {
  const value = String(mode || "").toLowerCase();
  if (value.includes("insert")) return "insert";
  if (value.includes("visual block")) return "visual-block";
  if (value.includes("visual line")) return "visual-line";
  if (value.includes("visual")) return "visual";
  return "normal";
}
