from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from judge.core.submission_status import command_status
from judge.utils.fs import read_json
from judge.utils.process import CommandResult, run_command_result


def warm_up_submission(
    command: list[str],
    data_dir: Path,
    run_dir: Path,
    timeout_ms: int,
    profile: str,
    emit: Callable[[str], None],
    command_runner: Callable[..., CommandResult] = run_command_result,
) -> dict[str, Any] | None:
    """Run the prepared submission once on the first case of a warmup profile."""
    manifest = read_json(data_dir / "manifest.json")
    cases = list(manifest.get("cases") or [])
    if not cases:
        emit(f"Skipping warmup for profile {profile}: no cases.")
        return None
    case = cases[0]
    case_id = case["id"]
    in_path = data_dir / case["input"]
    actual_path = run_dir / "warmup" / f"{profile}-{case_id}.actual"
    emit(f"Warming up submission with {profile} case {case_id}.")
    command_result = command_runner(
        command,
        timeout_ms,
        input_path=in_path,
        output_path=actual_path,
    )
    status, message = command_status(command_result)
    emit(f"Warmup case {case_id}: {status}.")
    return {
        "profile": profile,
        "case": case_id,
        "status": status,
        "message": message,
        "timeMs": command_result.elapsed_ms,
        "memoryBytes": command_result.memory_bytes,
    }
