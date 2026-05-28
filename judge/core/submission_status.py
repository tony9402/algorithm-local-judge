from __future__ import annotations

from judge.utils.process import CommandResult


def user_memory_limit_bytes(limits: dict[str, object]) -> int | None:
    """Return the configured user memory limit in bytes, if present."""
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
    """Return the judge status/message for a raw user command result."""
    if command_result.returncode == 124:
        return "time_limit", "time limit exceeded"
    if command_result.returncode != 0:
        return "runtime_error", command_result.stderr.decode("utf-8", errors="replace")
    return "ok", ""
