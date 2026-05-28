const app = window.AljApp;

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

function highlightToken(token, language) {
  const isComment = token.startsWith("//") || token.startsWith("/*") || token.startsWith("#");
  if (isComment) return `<span class="hl-comment">${token}</span>`;
  if (token.startsWith('"') || token.startsWith("'")) {
    return `<span class="hl-string">${token}</span>`;
  }
  if (/^\d/.test(token)) return `<span class="hl-number">${token}</span>`;
  return `<span class="hl-keyword">${token}</span>`;
}

function highlightCode(source, language) {
  const escaped = escapeHtml(source || " ");
  const commonNumber = "\\b\\d+(?:\\.\\d+)?\\b";
  const cppKeywords =
    "alignas|alignof|auto|bool|break|case|catch|char|class|const|constexpr|continue|decltype|default|delete|do|double|else|enum|explicit|extern|false|float|for|friend|if|inline|int|long|namespace|new|nullptr|operator|private|protected|public|return|short|signed|sizeof|static|struct|switch|template|this|throw|true|try|typedef|typename|using|void|while|vector|string|pair|map|set|queue|stack|priority_queue";
  const javaKeywords =
    "abstract|assert|boolean|break|byte|case|catch|char|class|const|continue|default|do|double|else|enum|extends|false|final|finally|float|for|if|implements|import|instanceof|int|interface|long|new|null|package|private|protected|public|return|short|static|super|switch|this|throw|throws|true|try|void|while|String|System";
  const pyKeywords =
    "False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield|print|range|len|int|str|list|dict|set|tuple";
  const languageKey = (language || "").toLowerCase();
  const keywordPattern = languageKey.includes("python")
    ? pyKeywords
    : languageKey.includes("java")
      ? javaKeywords
      : cppKeywords;
  const tokenPattern = languageKey.includes("python")
    ? new RegExp(
        `(#.*|"""[\\s\\S]*?"""|'''[\\s\\S]*?'''|"(?:\\\\.|[^"\\\\])*"|'(?:\\\\.|[^'\\\\])*'|\\b(?:${keywordPattern})\\b|${commonNumber})`,
        "g"
      )
    : new RegExp(
        `(//.*|/\\*[\\s\\S]*?\\*/|"(?:\\\\.|[^"\\\\])*"|'(?:\\\\.|[^'\\\\])*'|\\b(?:${keywordPattern})\\b|${commonNumber})`,
        "g"
      );
  return escaped.replace(tokenPattern, (token) => highlightToken(token, languageKey));
}

function updateCodeHighlight() {
  const input = app.optional("sourceTextInput");
  const highlight = app.optional("sourceHighlight");
  if (!input || !highlight) return;
  highlight.innerHTML = highlightCode(input.value, app.$("editorLanguageLabel").textContent);
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
  insertEditorText,
  syncEditorScroll,
  updateCodeHighlight,
  updateEditorLineNumbers,
  updateEditorView,
});
