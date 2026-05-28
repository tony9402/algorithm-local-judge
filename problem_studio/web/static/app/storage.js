/**
 * readStorage 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} key `key` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function readStorage(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/**
 * writeStorage 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} key `key` 값입니다.
 * @param {any} value 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function writeStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Local storage may be unavailable in restricted browser contexts.
  }
}

/**
 * removeStorage 함수를 실행하고 반환 값을 계산합니다.
 *
 * @param {any} key `key` 값입니다.
 * @returns {any} 처리 결과를 반환합니다.
 */
export function removeStorage(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Local storage may be unavailable in restricted browser contexts.
  }
}
