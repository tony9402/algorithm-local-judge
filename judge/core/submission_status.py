"""submission_status 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from judge.utils.process import CommandResult


def user_memory_limit_bytes(limits: dict[str, object]) -> int | None:
    """user_memory_limit_bytes 함수를 실행하고 결과를 반환합니다.
    
    Args:
        limits (dict[str, object]): `limits` 값입니다.
    
    Returns:
        int | None: 처리 결과를 반환합니다.
    """
    for key in ("userMemoryLimitBytes", "memoryLimitBytes"):
        value = limits.get(key)
        if isinstance(value, int) and value > 0:
            return value
    for key in ("userMemoryLimitMb", "memoryLimitMb"):
        value = limits.get(key)
        if isinstance(value, int) and value > 0:
            return value * 1024 * 1024
    return None


def command_status(command_result: CommandResult) -> tuple[str, str]:
    """command_status 함수를 실행하고 결과를 반환합니다.
    
    Args:
        command_result (CommandResult): `command_result` 값입니다.
    
    Returns:
        tuple[str, str]: 처리 결과를 반환합니다.
    """
    if command_result.returncode == 124:
        return "time_limit", "time limit exceeded"
    if command_result.returncode != 0:
        return "runtime_error", command_result.stderr.decode("utf-8", errors="replace")
    return "ok", ""
