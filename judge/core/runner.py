from __future__ import annotations

from pathlib import Path

from judge.core.errors import JudgeError
from judge.utils.process import run_command


def validator_check(validator: Path, input_path: Path, timeout_ms: int) -> None:
    """Run the validator against a generated input file."""
    code, _, stderr = run_command([str(validator)], timeout_ms, input_path=input_path)
    if code != 0:
        raise JudgeError(
            f"validator failed for {input_path.name}: {stderr.decode('utf-8', errors='replace')}"
        )


def solution_write(solution: Path, input_path: Path, answer_path: Path, timeout_ms: int) -> None:
    """Run the reference solution and write the expected answer file."""
    code, _, stderr = run_command(
        [str(solution)], timeout_ms, input_path=input_path, output_path=answer_path
    )
    if code != 0:
        raise JudgeError(
            f"solution failed for {input_path.name}: {stderr.decode('utf-8', errors='replace')}"
        )


def checker_compare(
    checker: Path, input_path: Path, output_path: Path, answer_path: Path, timeout_ms: int
) -> tuple[int, str]:
    """Run the checker and return its exit code plus stderr message."""
    code, _, stderr = run_command(
        [str(checker), str(input_path), str(output_path), str(answer_path)], timeout_ms
    )
    return code, stderr.decode("utf-8", errors="replace")
