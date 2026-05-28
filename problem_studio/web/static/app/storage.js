/**
 * storage 화면의 상태 갱신과 사용자 동작 처리를 담당하는 브라우저 모듈입니다.
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
 * storage 데이터를 지정된 파일이나 응답 대상에 기록합니다.
 *
 * @param {any} key 상태 맵, 로컬 스토리지, 객체에서 값을 찾는 키입니다.
 * @param {any} value 검증하거나 상태에 반영할 입력 값입니다.
 */
export function writeStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Local storage may be unavailable in restricted browser contexts.
  }
}
/**
 * storage 항목을 현재 상태와 저장소에서 제거합니다.
 *
 * @param {any} key 상태 맵, 로컬 스토리지, 객체에서 값을 찾는 키입니다.
 */
export function removeStorage(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Local storage may be unavailable in restricted browser contexts.
  }
}
