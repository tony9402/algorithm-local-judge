"""macOS/Linux에서 로컬 웹 앱의 백그라운드 프로세스를 안전하게 관리합니다."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

from alj_core.errors import JudgeError
from alj_core.paths import user_data_root

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows에는 백그라운드 서비스 명령을 제공하지 않습니다.
    fcntl = None  # type: ignore[assignment]


SERVICE_STATE_VERSION = 1
SERVICE_START_TIMEOUT_SECONDS = 15.0
SERVICE_STOP_TIMEOUT_SECONDS = 8.0
SERVICE_KILL_TIMEOUT_SECONDS = 2.0
SERVICE_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
SERVICE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


@dataclass(frozen=True)
class WebServiceSpec:
    """백그라운드 웹 앱을 식별하고 다시 실행하는 데 필요한 고정 정보입니다."""

    name: str
    display_name: str
    module: str
    health_app: str

    def __post_init__(self) -> None:
        if not SERVICE_NAME_RE.fullmatch(self.name):
            raise ValueError(f"invalid web service name: {self.name}")


def _require_supported_platform() -> None:
    if os.name != "posix" or fcntl is None:
        raise JudgeError("백그라운드 web 명령은 macOS와 Linux에서만 지원합니다.")


def _service_directory() -> Path:
    return user_data_root() / "services"


def service_state_path(spec: WebServiceSpec) -> Path:
    """서비스의 PID와 재시작 설정이 저장되는 경로를 반환합니다."""
    return _service_directory() / f"{spec.name}.json"


def service_log_path(spec: WebServiceSpec) -> Path:
    """백그라운드 서버의 표준 출력과 오류 로그 경로를 반환합니다."""
    return user_data_root() / "logs" / f"{spec.name}.log"


def _lock_path(spec: WebServiceSpec) -> Path:
    return _service_directory() / f"{spec.name}.lock"


@contextmanager
def _service_lock(spec: WebServiceSpec) -> Iterator[None]:
    _require_supported_platform()
    path = _lock_path(spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        assert fcntl is not None
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _atomic_write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validated_state(spec: WebServiceSpec, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise JudgeError(f"{spec.display_name} 서비스 상태 파일이 손상되었습니다.")
    pid = raw.get("pid")
    token = raw.get("token")
    child_args = raw.get("childArgs")
    if (
        raw.get("schemaVersion") != SERVICE_STATE_VERSION
        or raw.get("service") != spec.name
        or not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 1
        or not isinstance(token, str)
        or SERVICE_TOKEN_RE.fullmatch(token) is None
        or not isinstance(child_args, list)
        or not all(isinstance(item, str) for item in child_args)
        or "--service-runner" in child_args
        or not isinstance(raw.get("host"), str)
        or not isinstance(raw.get("port"), int)
        or isinstance(raw.get("port"), bool)
        or not isinstance(raw.get("openBrowser"), bool)
    ):
        raise JudgeError(f"{spec.display_name} 서비스 상태 파일이 손상되었습니다.")
    return raw


def _load_state(spec: WebServiceSpec) -> dict[str, Any] | None:
    path = service_state_path(spec)
    if not path.exists():
        return None
    if path.is_symlink():
        raise JudgeError(f"심볼릭 링크 서비스 상태 파일은 사용할 수 없습니다: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JudgeError(
            f"{spec.display_name} 서비스 상태 파일을 읽을 수 없습니다: {path}"
        ) from exc
    return _validated_state(spec, raw)


def _remove_state(spec: WebServiceSpec) -> None:
    path = service_state_path(spec)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_command(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True,
            capture_output=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise JudgeError(f"PID {pid} 프로세스의 소유권을 확인할 수 없습니다.") from exc
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _process_matches_state(state: dict[str, Any]) -> bool:
    pid = int(state["pid"])
    if not _process_is_alive(pid):
        return False
    command = _process_command(pid)
    if command is None:
        return False
    return f"--service-runner {state['token']}" in command


def _launcher_command(spec: WebServiceSpec) -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    return [sys.executable, "-m", spec.module]


def _connect_host(host: str) -> str:
    normalized = host.strip().lower()
    if normalized in {"0.0.0.0", "*"}:
        return "127.0.0.1"
    if normalized in {"::", "[::]"}:
        return "::1"
    return host


def _service_url(host: str, port: int) -> str:
    connect_host = _connect_host(host)
    formatted_host = (
        f"[{connect_host}]"
        if ":" in connect_host and not connect_host.startswith("[")
        else connect_host
    )
    return f"http://{formatted_host}:{port}"


def _health_matches(url: str, expected_app: str) -> bool:
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(f"{url}/healthz", timeout=0.5) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("app") == expected_app


def _log_tail(path: Path, limit: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:].strip()


def _terminate_spawned_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _wait_for_start(
    process: subprocess.Popen[Any],
    spec: WebServiceSpec,
    url: str,
    log_path: Path,
) -> None:
    started = time.monotonic()
    deadline = started + SERVICE_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            detail = _log_tail(log_path)
            suffix = f"\n{detail}" if detail else ""
            raise JudgeError(
                f"{spec.display_name} 시작에 실패했습니다 (exit {return_code}). "
                f"로그: {log_path}{suffix}"
            )
        if time.monotonic() - started >= 0.4 and _health_matches(url, spec.health_app):
            return
        time.sleep(0.1)
    raise JudgeError(
        f"{spec.display_name}가 {SERVICE_START_TIMEOUT_SECONDS:g}초 안에 준비되지 않았습니다. "
        f"로그: {log_path}"
    )


def _start_locked(
    spec: WebServiceSpec,
    *,
    child_args: list[str],
    host: str,
    port: int,
    open_browser: bool,
) -> dict[str, Any]:
    if not 1 <= port <= 65535:
        raise JudgeError(f"web port는 1~65535 범위여야 합니다: {port}")
    existing = _load_state(spec)
    if existing is not None:
        if _process_matches_state(existing):
            raise JudgeError(
                f"{spec.display_name}가 이미 실행 중입니다 "
                f"(PID {existing['pid']}, {existing.get('url', '')})."
            )
        _remove_state(spec)

    token = uuid.uuid4().hex
    log_path = service_log_path(spec)
    if log_path.is_symlink():
        raise JudgeError(f"심볼릭 링크 서비스 로그 파일은 사용할 수 없습니다: {log_path}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        *_launcher_command(spec),
        "web",
        "--service-runner",
        token,
        *child_args,
    ]
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n=== {datetime.now(UTC).isoformat()} start ===\n")
        log.flush()
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment,
            close_fds=True,
            start_new_session=True,
        )

    url = _service_url(host, port)
    state = {
        "schemaVersion": SERVICE_STATE_VERSION,
        "service": spec.name,
        "pid": process.pid,
        "token": token,
        "host": host,
        "port": port,
        "url": url,
        "logPath": str(log_path),
        "childArgs": list(child_args),
        "openBrowser": bool(open_browser),
        "startedAt": datetime.now(UTC).isoformat(),
    }
    try:
        _atomic_write_state(service_state_path(spec), state)
        _wait_for_start(process, spec, url, log_path)
    except BaseException:
        _terminate_spawned_process(process)
        _remove_state(spec)
        raise
    if open_browser:
        try:
            webbrowser.open(url)
        except OSError:
            pass
    return state


def start_web_service(
    spec: WebServiceSpec,
    *,
    child_args: list[str],
    host: str,
    port: int,
    open_browser: bool,
) -> dict[str, Any]:
    """웹 앱을 새 세션에서 시작하고 health endpoint가 준비될 때까지 기다립니다."""
    with _service_lock(spec):
        return _start_locked(
            spec,
            child_args=child_args,
            host=host,
            port=port,
            open_browser=open_browser,
        )


def _wait_until_stopped(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _process_is_alive(pid):
            return True
        time.sleep(0.1)
    return not _process_is_alive(pid)


def _stop_locked(spec: WebServiceSpec) -> dict[str, Any]:
    state = _load_state(spec)
    if state is None:
        return {"status": "not-running"}
    pid = int(state["pid"])
    if not _process_is_alive(pid):
        _remove_state(spec)
        return {"status": "not-running", "stale": True}
    if not _process_matches_state(state):
        _remove_state(spec)
        return {"status": "not-running", "stale": True, "unrelatedPid": pid}

    os.kill(pid, signal.SIGTERM)
    if not _wait_until_stopped(pid, SERVICE_STOP_TIMEOUT_SECONDS):
        if not _process_matches_state(state):
            raise JudgeError(
                f"{spec.display_name} 종료 중 PID 소유권이 변경되어 강제 종료하지 않았습니다."
            )
        os.kill(pid, signal.SIGKILL)
        if not _wait_until_stopped(pid, SERVICE_KILL_TIMEOUT_SECONDS):
            raise JudgeError(f"{spec.display_name} 프로세스 PID {pid}를 종료하지 못했습니다.")
    _remove_state(spec)
    return {"status": "stopped", "pid": pid}


def stop_web_service(spec: WebServiceSpec) -> dict[str, Any]:
    """소유권 토큰이 일치하는 백그라운드 웹 프로세스만 종료합니다."""
    with _service_lock(spec):
        return _stop_locked(spec)


def web_service_status(spec: WebServiceSpec) -> dict[str, Any]:
    """저장된 PID의 소유권과 health endpoint를 확인해 현재 서비스 상태를 반환합니다."""
    with _service_lock(spec):
        state = _load_state(spec)
        if state is None:
            return {"status": "not-running"}
        pid = int(state["pid"])
        if not _process_is_alive(pid):
            _remove_state(spec)
            return {"status": "not-running", "stale": True}
        if not _process_matches_state(state):
            _remove_state(spec)
            return {
                "status": "not-running",
                "stale": True,
                "unrelatedPid": pid,
            }
        return {
            **state,
            "status": "running",
            "healthy": _health_matches(str(state["url"]), spec.health_app),
        }


def _replace_child_option(child_args: list[str], option: str, value: str) -> list[str]:
    updated = list(child_args)
    try:
        index = updated.index(option)
    except ValueError:
        updated.extend([option, value])
    else:
        if index + 1 >= len(updated):
            raise JudgeError(f"저장된 {option} 서비스 옵션이 손상되었습니다.")
        updated[index + 1] = value
    return updated


def restart_web_service(
    spec: WebServiceSpec,
    *,
    child_args: list[str],
    host: str,
    port: int,
    open_browser: bool,
    port_override: int | None = None,
) -> dict[str, Any]:
    """실행 중인 서비스를 종료하고 마지막 시작 설정으로 다시 시작합니다."""
    with _service_lock(spec):
        previous = _load_state(spec)
        if previous is not None:
            child_args = list(previous["childArgs"])
            host = str(previous["host"])
            port = int(previous["port"])
            open_browser = bool(previous["openBrowser"])
        if port_override is not None:
            port = port_override
            child_args = _replace_child_option(child_args, "--port", str(port_override))
        _stop_locked(spec)
        return _start_locked(
            spec,
            child_args=child_args,
            host=host,
            port=port,
            open_browser=open_browser,
        )


def has_saved_web_service(spec: WebServiceSpec) -> bool:
    """restart가 재사용할 저장 설정이 있는지 확인합니다."""
    return service_state_path(spec).is_file()


__all__ = [
    "WebServiceSpec",
    "has_saved_web_service",
    "restart_web_service",
    "service_log_path",
    "service_state_path",
    "start_web_service",
    "stop_web_service",
    "web_service_status",
]
