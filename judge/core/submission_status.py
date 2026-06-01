"""제출 상태 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from judge.utils.process import CommandResult

DEFAULT_USER_MEMORY_LIMIT_MB = 2048
DEFAULT_USER_MEMORY_LIMIT_BYTES = DEFAULT_USER_MEMORY_LIMIT_MB * 1024 * 1024


def user_memory_limit_bytes(limits: dict[str, object]) -> int | None:
    for key in ("userMemoryLimitBytes", "memoryLimitBytes"):
        value = limits.get(key)
        if isinstance(value, int) and value > 0:
            return value
    for key in ("userMemoryLimitMb", "memoryLimitMb"):
        value = limits.get(key)
        if isinstance(value, int) and value > 0:
            return value * 1024 * 1024
    return DEFAULT_USER_MEMORY_LIMIT_BYTES


def command_status(command_result: CommandResult) -> tuple[str, str]:
    if command_result.returncode == 124:
        return "time_limit", "time limit exceeded"
    if command_result.returncode != 0:
        return "runtime_error", command_result.stderr.decode("utf-8", errors="replace")
    return "ok", ""
