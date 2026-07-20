"""로컬 웹 작업 이력을 사용자 데이터 디렉터리의 atomic JSON 파일에 저장합니다."""

from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

if os.name == "nt":  # pragma: no cover - exercised on Windows CI
    import msvcrt
else:  # pragma: no cover - import branch is platform-specific
    import fcntl

APP_DATA_DIR_NAME = "algorithm-local-judge"
JOB_HISTORY_DIR_NAME = "jobs"


def local_data_root() -> Path:
    """환경 설정 또는 운영체제 표준 위치에서 로컬 사용자 데이터 루트를 계산합니다."""
    if configured := os.environ.get("ALJ_DATA_HOME"):
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        value = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base = Path(value).expanduser() if value else Path.home() / "AppData" / "Local"
        return (base / APP_DATA_DIR_NAME).resolve()
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (base / APP_DATA_DIR_NAME).expanduser().resolve()


def default_job_history_path(app_name: str) -> Path:
    """애플리케이션별로 충돌하지 않는 작업 이력 JSON 경로를 반환합니다."""
    safe_name = "".join(
        character for character in app_name if character.isalnum() or character in "-_"
    )
    if not safe_name:
        raise ValueError("job history app name must contain a safe character")
    return local_data_root() / JOB_HISTORY_DIR_NAME / f"{safe_name}.json"


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    return str(value)


class AtomicJsonFile:
    """한 프로세스의 상태 스냅샷을 임시 파일과 ``os.replace``로 안전하게 교체합니다."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser().resolve()
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        self.last_error: str | None = None

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.path.parent.chmod(0o700)
        with self.lock_path.open("a+b") as lock:
            if os.name == "nt":
                lock.seek(0)
                lock.write(b"0")
                lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                self.lock_path.chmod(0o600)
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def read(self) -> Any | None:
        """파일이 없으면 ``None``을, 손상됐으면 격리 후 ``None``을 반환합니다."""
        if not self.path.exists():
            return None
        try:
            # Reads observe a complete snapshot because writers use os.replace.
            # Avoid creating a lock file during module import; read-only or
            # sandboxed installations may not permit creating files beside the
            # existing history file.
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            try:
                self._quarantine_unlocked(f"unable to load job history: {exc}")
            except OSError:
                self.last_error = f"unable to quarantine job history: {exc}"
            return None

    def write(self, payload: Any) -> bool:
        """JSON 스냅샷을 같은 디렉터리에서 기록한 뒤 원본 경로로 atomic 교체합니다."""
        temporary_path: Path | None = None
        try:
            with self._locked():
                temporary_path = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
                serialized = json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    default=_json_default,
                )
                with temporary_path.open("w", encoding="utf-8") as output:
                    if os.name != "nt":
                        temporary_path.chmod(0o600)
                    output.write(serialized)
                    output.write("\n")
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary_path, self.path)
            self.last_error = None
            return True
        except (OSError, TypeError, ValueError) as exc:
            self.last_error = f"unable to persist job history: {exc}"
            return False
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def quarantine(self, error: str) -> Path | None:
        """손상된 파일을 보존 가능한 별도 이름으로 옮기고 오류를 기록합니다."""
        try:
            with self._locked():
                return self._quarantine_unlocked(error)
        except OSError:
            self.last_error = error
            return None

    def _quarantine_unlocked(self, error: str) -> Path | None:
        self.last_error = error
        if not self.path.exists():
            return None
        suffix = datetime.now().strftime("%Y%m%d%H%M%S%f")
        quarantine_path = self.path.with_name(f"{self.path.name}.corrupt-{suffix}")
        try:
            os.replace(self.path, quarantine_path)
        except OSError:
            return None
        return quarantine_path


__all__ = [
    "AtomicJsonFile",
    "default_job_history_path",
    "local_data_root",
]
