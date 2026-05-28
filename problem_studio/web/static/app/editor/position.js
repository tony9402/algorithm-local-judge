/**
 * lineStartAt 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function lineStartAt(value, position) {
  return value.lastIndexOf("\n", Math.max(0, position - 1)) + 1;
}

/**
 * lineEndAt 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function lineEndAt(value, position) {
  const nextBreak = value.indexOf("\n", position);
  return nextBreak === -1 ? value.length : nextBreak;
}

/**
 * firstTextColumn 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} lineStart `lineStart` 값입니다.
 * @param {any} lineEnd `lineEnd` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function firstTextColumn(value, lineStart, lineEnd = lineEndAt(value, lineStart)) {
  const match = value.slice(lineStart, lineEnd).match(/\S/);
  return match ? lineStart + match.index : lineStart;
}

/**
 * currentLineIndent 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function currentLineIndent(value, position) {
  const lineStart = lineStartAt(value, position);
  const lineEnd = lineEndAt(value, position);
  return value.slice(lineStart, firstTextColumn(value, lineStart, lineEnd));
}

/**
 * normalLineCursorEnd 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} lineStart `lineStart` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function normalLineCursorEnd(value, lineStart) {
  const lineEnd = lineEndAt(value, lineStart);
  return lineEnd > lineStart ? lineEnd - 1 : lineStart;
}

/**
 * clampNormalCursor 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function clampNormalCursor(value, position) {
  if (!value) return 0;
  let bounded = Math.max(0, Math.min(position, value.length - 1));
  const lineStart = lineStartAt(value, bounded);
  const lineEnd = lineEndAt(value, bounded);
  if (bounded >= lineEnd && lineEnd > lineStart) bounded = lineEnd - 1;
  if (value[bounded] === "\n" && lineEnd > lineStart) bounded = lineEnd - 1;
  return Math.max(lineStart, bounded);
}

/**
 * normalCursorEndAt 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function normalCursorEndAt(value, position) {
  return normalLineCursorEnd(value, lineStartAt(value, position));
}

/**
 * editorLineColumn 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function editorLineColumn(value, position) {
  const lineStart = lineStartAt(value, position);
  const line = value.slice(0, position).split("\n").length;
  return { lineStart, line, column: position - lineStart };
}

/**
 * currentLineBounds 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function currentLineBounds(value, position) {
  const start = lineStartAt(value, position);
  const end = lineEndAt(value, position);
  return { start, end };
}

/**
 * lineStartByNumber 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} lineNumber `lineNumber` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function lineStartByNumber(value, lineNumber) {
  if (lineNumber <= 1) return 0;
  let position = 0;
  for (let line = 1; line < lineNumber; line += 1) {
    const next = value.indexOf("\n", position);
    if (next === -1) return value.length;
    position = next + 1;
  }
  return position;
}

/**
 * totalLineCount 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function totalLineCount(value) {
  return Math.max(1, value.split("\n").length);
}

/**
 * currentLineNumber 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function currentLineNumber(value, position) {
  return value.slice(0, position).split("\n").length;
}

/**
 * lineWithBreakBounds 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function lineWithBreakBounds(value, position) {
  let { start, end } = currentLineBounds(value, position);
  if (end < value.length) {
    end += 1;
  } else if (start > 0) {
    start -= 1;
  }
  return { start, end };
}

/**
 * lineRangeWithBreakBounds 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @param {any} count `count` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function lineRangeWithBreakBounds(value, position, count = 1) {
  let start = lineStartAt(value, position);
  let end = start;
  for (let index = 0; index < count; index += 1) {
    end = lineEndAt(value, end);
    if (end < value.length) {
      end += 1;
    } else {
      break;
    }
  }
  return { start, end };
}

/**
 * nextWordPosition 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function nextWordPosition(value, position) {
  const rest = value.slice(Math.min(position + 1, value.length));
  const match = rest.match(/\b\w/);
  return match ? position + 1 + match.index : position;
}

/**
 * previousWordPosition 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function previousWordPosition(value, position) {
  const before = value.slice(0, Math.max(0, position));
  const matches = [...before.matchAll(/\b\w/g)];
  return matches.length ? matches[matches.length - 1].index || 0 : position;
}

/**
 * nextWordEndIndex 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} value 값입니다.
 * @param {any} position `position` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function nextWordEndIndex(value, position) {
  let cursor = Math.max(0, Math.min(position + 1, value.length));
  while (cursor < value.length && /\s/.test(value[cursor])) cursor += 1;
  while (cursor < value.length && /\w/.test(value[cursor])) cursor += 1;
  return Math.max(0, Math.min(value.length, cursor - 1));
}
