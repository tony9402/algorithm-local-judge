"""컴파일러 common 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alj_core.config import COMPILE_FLAGS
from alj_core.errors import JudgeError
from alj_core.paths import rel
from alj_core.toolchains import resolve_tool as resolve_toolchain_tool
from alj_core.utils.process import run_command

CPP_SUFFIXES = {".cpp", ".cc", ".cxx"}
PYTHON_SUFFIXES = {".py"}
JAVA_SUFFIXES = {".java"}
SUPPORTED_USER_SUFFIXES = CPP_SUFFIXES | PYTHON_SUFFIXES | JAVA_SUFFIXES
JAVA_PUBLIC_CLASS_RE = re.compile(r"\bpublic\s+class\s+([A-Za-z_][A-Za-z0-9_]*)")
COMPILE_OUTPUT_LIMIT = 6000
COMPILER_IDENTITY_TIMEOUT_MS = 2000

_COMPILER_IDENTITY_LOCK = threading.Lock()
_COMPILER_IDENTITY_CACHE: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}


@dataclass(frozen=True)
class PreparedSubmission:
    """prepared 제출 상태와 관련 동작을 하나의 객체로 표현합니다."""

    command: list[str]
    language: str


def compile_cpp(
    source: Path, output: Path, include_root: Path, timeout_ms: int, log_path: Path
) -> dict[str, Any]:
    """cpp 실행에 필요한 명령을 만들고 프로세스 종료 상태와 오류 출력을 해석합니다.

    Args:
        source (Path): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
        output (Path): cpp을 계산하거나 검증할 때 필요한 출력 입력입니다.
        include_root (Path): cpp을 계산하거나 검증할 때 필요한 include root 입력입니다.
        timeout_ms (int): 외부 프로세스가 끝나야 하는 제한 시간입니다. 단위는 밀리초입니다.
        log_path (Path): log 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 cpp 데이터입니다.
    """
    include_paths = [include_root]
    problems_include = include_root / "problems"
    if problems_include.exists():
        include_paths.append(problems_include)
    cxx = resolve_tool("ALJ_CXX", ["g++"])
    command = [
        cxx,
        *COMPILE_FLAGS,
        *(flag for include_path in include_paths for flag in ("-I", str(include_path))),
        str(source),
        "-o",
        str(output),
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    code, _, stderr = run_command(command, timeout_ms, log_path=log_path)
    if code != 0:
        raise JudgeError(compile_error_message("compile failed", source, log_path, stderr))
    return {"command": command, "stderr": stderr.decode("utf-8", errors="replace")}


def compile_error_message(label: str, source: Path, log_path: Path, stderr: bytes) -> str:
    """오류 message 소스와 설정을 실행 가능한 산출물과 진단 정보로 변환합니다.

    Args:
        label (str): 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
        source (Path): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
        log_path (Path): log 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        stderr (bytes): 외부 프로세스가 표준 오류로 출력한 바이트 데이터입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 오류 message 문자열입니다.
    """
    text = stderr.decode("utf-8", errors="replace").strip()
    if len(text) > COMPILE_OUTPUT_LIMIT:
        text = text[-COMPILE_OUTPUT_LIMIT:]
        text = f"...truncated...\n{text}"
    message = f"{label}: {rel(source)}\nlog: {rel(log_path)}"
    if text:
        message += f"\n\ncompiler output:\n{text}"
    return message


def resolve_tool(env_name: str, candidates: list[str]) -> str:
    """도구 식별자나 상대 경로를 실제 사용할 수 있는 대상으로 확정합니다.

    Args:
        env_name (str): env 이름를 사용자 표시와 내부 조회에 함께 사용하는 이름입니다.
        candidates (list[str]): 도구을 계산하거나 검증할 때 필요한 candidates 입력입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 도구 문자열입니다.
    """
    return resolve_toolchain_tool(env_name, candidates)


def compiler_identity(
    env_name: str,
    candidates: list[str],
    version_args: list[str] | None = None,
) -> dict[str, Any]:
    """컴파일 캐시 입력으로 사용할 실제 도구 경로와 버전 출력을 계산합니다."""
    resolved = resolve_tool(env_name, candidates)
    args = tuple(version_args or ["--version"])
    cache_key = (env_name, resolved, args)
    with _COMPILER_IDENTITY_LOCK:
        cached = _COMPILER_IDENTITY_CACHE.get(cache_key)
        if cached is not None:
            return cached
    code, stdout, stderr = run_command([resolved, *args], COMPILER_IDENTITY_TIMEOUT_MS)
    version_text = (stdout + (b"\n" if stdout and stderr else b"") + stderr).decode(
        "utf-8",
        errors="replace",
    )
    identity = {
        "env": env_name,
        "path": resolved,
        "versionArgs": list(args),
        "versionReturnCode": code,
        "version": version_text[:4000],
    }
    with _COMPILER_IDENTITY_LOCK:
        _COMPILER_IDENTITY_CACHE[cache_key] = identity
    return identity


def java_main_class(source: Path) -> str:
    """java main class 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        source (Path): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 java main class 문자열입니다.
    """
    match = JAVA_PUBLIC_CLASS_RE.search(source.read_text(encoding="utf-8", errors="replace"))
    if match:
        return match.group(1)
    return source.stem
