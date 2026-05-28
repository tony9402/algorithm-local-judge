"""프로세스 기능을 담당하는 모듈입니다.
"""
from __future__ import annotations

import os
import platform
import signal
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    """명령 결과에 필요한 필드를 한데 묶어 전달하는 데이터 모델입니다.
    """

    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed_ms: int
    memory_bytes: int | None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    output_truncated: bool = False


DEFAULT_CAPTURE_LIMIT_BYTES = 1024 * 1024
DEFAULT_FILE_OUTPUT_LIMIT_BYTES = 10 * 1024 * 1024
PROCESS_GROUP_KILL_GRACE_SECONDS = 0.2


class MemorySampler:
    """메모리 sampler 상태와 관련 동작을 하나의 객체로 표현합니다.
    """

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.max_bytes: int | None = process_memory_bytes(pid)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> int | None:
        self._stop.set()
        self._thread.join(timeout=0.5)
        return self.max_bytes

    def _sample(self) -> None:
        while not self._stop.is_set():
            memory = process_memory_bytes(self.pid)
            if memory is not None:
                self.max_bytes = memory if self.max_bytes is None else max(self.max_bytes, memory)
            self._stop.wait(0.05)


def process_memory_bytes(pid: int) -> int | None:
    system = platform.system()
    if system == "Linux":
        return linux_process_memory_bytes(pid)
    if system == "Darwin":
        return darwin_process_memory_bytes(pid)
    return None


def linux_process_memory_bytes(pid: int) -> int | None:
    """linux 프로세스 메모리 바이트 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

        Args:
            pid (int): linux 프로세스 메모리 바이트을 계산하거나 검증할 때 필요한 pid 입력입니다.
    """
    status = Path(f"/proc/{pid}/status")
    try:
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith(("VmHWM:", "VmRSS:")):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) * 1024
    except OSError:
        return None
    return None


def darwin_process_memory_bytes(pid: int) -> int | None:
    """darwin 프로세스 메모리 바이트 실행에 필요한 명령을 만들고 프로세스 종료 상태와 오류 출력을 해석합니다.

        Args:
            pid (int): darwin 프로세스 메모리 바이트을 계산하거나 검증할 때 필요한 pid 입력입니다.
    """
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=0.2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    text = result.stdout.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        return int(text.splitlines()[0].strip()) * 1024
    except ValueError:
        return None


def truncated_bytes(data: bytes, limit: int, label: str) -> tuple[bytes, bool]:
    if limit <= 0:
        return b"", bool(data)
    if len(data) <= limit:
        return data, False
    marker = f"\n... {label} truncated to {limit} bytes ...\n".encode()
    if len(marker) >= limit:
        return marker[:limit], True
    return data[: limit - len(marker)] + marker, True


def append_stderr_note(stderr: bytes, note: str, limit: int) -> tuple[bytes, bool]:
    suffix = (b"\n" if stderr else b"") + note.encode("utf-8")
    return truncated_bytes(stderr + suffix, limit, "stderr")


def truncate_output_file(path: Path, limit: int) -> bool:
    """truncate 출력 파일 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
        limit (int): truncate 출력 파일을 계산하거나 검증할 때 필요한 제한 입력입니다.

    Returns:
        bool: truncate 출력 파일 조건을 만족하면 True, 아니면 False입니다.
    """
    if limit <= 0:
        path.write_bytes(b"")
        return True
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size <= limit:
        return False
    with path.open("r+b") as output:
        output.truncate(limit)
    return True


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """terminate 프로세스 group 실행에 필요한 명령을 만들고 프로세스 종료 상태와 오류 출력을 해석합니다.

    Args:
        process (subprocess.Popen[bytes]): terminate 프로세스 group을 계산하거나 검증할 때 필요한 프로세스 입력입니다.
    """
    if process.poll() is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            process.terminate()
        try:
            process.wait(timeout=PROCESS_GROUP_KILL_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                return
            except OSError:
                process.kill()
            return
    process.kill()


def run_command_result(
    command: Sequence[str],
    timeout_ms: int | None,
    cwd: Path | None = None,
    input_path: Path | None = None,
    output_path: Path | None = None,
    log_path: Path | None = None,
    stdout_limit_bytes: int = DEFAULT_CAPTURE_LIMIT_BYTES,
    stderr_limit_bytes: int = DEFAULT_CAPTURE_LIMIT_BYTES,
    output_limit_bytes: int = DEFAULT_FILE_OUTPUT_LIMIT_BYTES,
) -> CommandResult:
    """명령 결과 실행에 필요한 명령을 만들고 프로세스 종료 상태와 오류 출력을 해석합니다.

        Args:
            command (Sequence[str]): 명령 결과을 계산하거나 검증할 때 필요한 명령 입력입니다.
            timeout_ms (int | None): 외부 프로세스가 끝나야 하는 제한 시간입니다. 단위는 밀리초입니다.
            cwd (Path | None): 명령 결과을 계산하거나 검증할 때 필요한 cwd 입력입니다.
            input_path (Path | None): 검증기, 솔루션, 체커에 전달할 테스트 입력 파일입니다.
            output_path (Path | None): 제출 프로그램이 생성한 실제 출력 파일입니다.
            log_path (Path | None): log 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
            stdout_limit_bytes (int): 명령 결과을 계산하거나 검증할 때 필요한 표준 출력 제한 바이트 입력입니다.
            stderr_limit_bytes (int): 명령 결과을 계산하거나 검증할 때 필요한 표준 오류 제한 바이트 입력입니다.
            output_limit_bytes (int): 명령 결과을 계산하거나 검증할 때 필요한 출력 제한 바이트 입력입니다.
    """
    stdin = None
    stdout = subprocess.PIPE
    start = time.perf_counter()
    process = None
    sampler = None
    try:
        if input_path is not None:
            stdin = input_path.open("rb")
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            stdout = output_path.open("wb")

        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=stdin,
            stdout=stdout,
            stderr=subprocess.PIPE,
            start_new_session=os.name != "nt",
        )
        sampler = MemorySampler(process.pid)
        sampler.start()
        try:
            stdout_data, stderr = process.communicate(
                timeout=timeout_ms / 1000 if timeout_ms else None
            )
            returncode = process.returncode
        except subprocess.TimeoutExpired as exc:
            terminate_process_group(process)
            stdout_data, stderr = process.communicate()
            returncode = 124
            timeout_message = str(exc).encode("utf-8")
            stderr = (stderr or b"") + (b"\n" if stderr else b"") + timeout_message
            if log_path:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(
                    f"timeout after {timeout_ms} ms\n{command}\n",
                    encoding="utf-8",
                )
        elapsed_ms = max(0, int(round((time.perf_counter() - start) * 1000)))
        memory_bytes = sampler.stop() if sampler is not None else None
    except OSError as exc:
        elapsed_ms = max(0, int(round((time.perf_counter() - start) * 1000)))
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(str(exc), encoding="utf-8")
        return CommandResult(127, b"", str(exc).encode("utf-8"), elapsed_ms, None)
    finally:
        if sampler is not None and process is not None and process.poll() is None:
            sampler.stop()
        if stdin is not None:
            stdin.close()
        if output_path is not None and hasattr(stdout, "close"):
            stdout.close()

    stdout_data = stdout_data or b""
    stderr = stderr or b""
    stdout_data, stdout_truncated = truncated_bytes(
        b"" if output_path is not None else stdout_data,
        stdout_limit_bytes,
        "stdout",
    )
    stderr, stderr_truncated = truncated_bytes(stderr, stderr_limit_bytes, "stderr")
    output_truncated = False
    if output_path is not None and output_path.exists():
        output_truncated = truncate_output_file(output_path, output_limit_bytes)
        if output_truncated:
            stderr, note_truncated = append_stderr_note(
                stderr,
                f"actual output truncated to {output_limit_bytes} bytes: {output_path}",
                stderr_limit_bytes,
            )
            stderr_truncated = stderr_truncated or note_truncated
    if log_path and returncode != 124:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_bytes(stderr)
    return CommandResult(
        returncode,
        stdout_data,
        stderr,
        elapsed_ms,
        memory_bytes,
        stdout_truncated,
        stderr_truncated,
        output_truncated,
    )


def run_command(
    command: Sequence[str],
    timeout_ms: int | None,
    cwd: Path | None = None,
    input_path: Path | None = None,
    output_path: Path | None = None,
    log_path: Path | None = None,
) -> tuple[int, bytes, bytes]:
    """명령 실행에 필요한 명령을 만들고 프로세스 종료 상태와 오류 출력을 해석합니다.

    Args:
        command (Sequence[str]): 명령을 계산하거나 검증할 때 필요한 명령 입력입니다.
        timeout_ms (int | None): 외부 프로세스가 끝나야 하는 제한 시간입니다. 단위는 밀리초입니다.
        cwd (Path | None): 명령을 계산하거나 검증할 때 필요한 cwd 입력입니다.
        input_path (Path | None): 검증기, 솔루션, 체커에 전달할 테스트 입력 파일입니다.
        output_path (Path | None): 제출 프로그램이 생성한 실제 출력 파일입니다.
        log_path (Path | None): log 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.

    Returns:
        tuple[int, bytes, bytes]: 명령 판단에 필요한 여러 값을 정해진 순서로 묶은 튜플입니다.
    """
    result = run_command_result(
        command,
        timeout_ms,
        cwd=cwd,
        input_path=input_path,
        output_path=output_path,
        log_path=log_path,
    )
    return result.returncode, result.stdout, result.stderr
