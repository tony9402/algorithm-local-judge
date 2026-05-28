from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge.core.runner import checker_compare
from judge.core.submission_result import copy_wrong_artifacts
from judge.core.submission_status import command_status, user_memory_limit_bytes
from judge.utils.process import CommandResult, run_command_result


@dataclass(frozen=True)
class SubmissionCasesResult:
    status: str
    results: list[dict[str, Any]]
    first_wrong: dict[str, Any] | None
    max_time_ms: int
    max_memory_bytes: int | None


def run_submission_cases(
    *,
    manifest: dict[str, Any],
    data_dir: Path,
    outputs_dir: Path,
    wrong_dir: Path,
    command: list[str],
    limits: dict[str, Any],
    checker_path: Path,
    emit: Callable[[str], None],
    stop_on_first_failure: bool,
    command_runner: Callable[..., CommandResult] = run_command_result,
    checker: Callable[[Path, Path, Path, Path, int], tuple[int, str]] = checker_compare,
) -> SubmissionCasesResult:
    """Run user code against compiled cases and capture judge status."""
    results: list[dict[str, Any]] = []
    status = "accepted"
    first_wrong = None
    max_time_ms = 0
    max_memory_bytes: int | None = None
    timeout_ms = limits.get("userTimeoutMs", 2000)
    memory_limit = user_memory_limit_bytes(limits)
    cases = manifest["cases"]

    for index, case in enumerate(cases, start=1):
        case_id = case["id"]
        emit(f"Running case {case_id} ({index}/{len(cases)}).")
        in_path = data_dir / case["input"]
        answer_path = data_dir / case["answer"]
        actual_path = outputs_dir / f"{case_id}.actual"
        command_result = command_runner(
            command,
            timeout_ms,
            input_path=in_path,
            output_path=actual_path,
        )
        max_time_ms = max(max_time_ms, command_result.elapsed_ms)
        if command_result.memory_bytes is not None:
            max_memory_bytes = (
                command_result.memory_bytes
                if max_memory_bytes is None
                else max(max_memory_bytes, command_result.memory_bytes)
            )
        case_status, message = command_status(command_result)
        if memory_limit is not None and (
            command_result.memory_bytes is not None and command_result.memory_bytes > memory_limit
        ):
            case_status = "memory_limit"
            message = "memory limit exceeded"
        elif case_status == "ok":
            checker_code, checker_message = checker(
                checker_path,
                in_path,
                actual_path,
                answer_path,
                timeout_ms,
            )
            if checker_code != 0:
                case_status = "wrong_answer"
                message = checker_message
        emit(f"Case {case_id}: {case_status}.")
        results.append(
            {
                "case": case_id,
                "status": case_status,
                "message": message,
                "timeMs": command_result.elapsed_ms,
                "memoryBytes": command_result.memory_bytes,
            }
        )
        if case_status != "ok":
            if first_wrong is None:
                status = case_status
                first_wrong = case
                copy_wrong_artifacts(wrong_dir, case_id, in_path, answer_path, actual_path)
            if stop_on_first_failure:
                break

    return SubmissionCasesResult(
        status=status,
        results=results,
        first_wrong=first_wrong,
        max_time_ms=max_time_ms,
        max_memory_bytes=max_memory_bytes,
    )


__all__ = [
    "SubmissionCasesResult",
    "run_submission_cases",
]
