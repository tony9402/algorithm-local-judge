from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from judge.core.paths import rel


def copy_wrong_artifacts(
    wrong_dir: Path,
    case_id: str,
    in_path: Path,
    answer_path: Path,
    actual_path: Path,
) -> None:
    """Copy the first failing case artifacts into the run directory."""
    wrong_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(in_path, wrong_dir / f"{case_id}.in")
    shutil.copyfile(answer_path, wrong_dir / f"{case_id}.expected")
    if actual_path.exists():
        shutil.copyfile(actual_path, wrong_dir / f"{case_id}.actual")
    else:
        (wrong_dir / f"{case_id}.actual").write_text("", encoding="utf-8")


def build_submission_result(
    *,
    run_id: str,
    problem_id: str,
    profile: str,
    language: str,
    status: str,
    cases: list[dict[str, Any]],
    max_time_ms: int,
    max_memory_bytes: int | None,
    warmup: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the serializable run result payload."""
    result = {
        "runId": run_id,
        "problemId": problem_id,
        "profile": profile,
        "language": language,
        "status": status,
        "cases": cases,
        "metrics": {
            "maxTimeMs": max_time_ms,
            "maxMemoryBytes": max_memory_bytes,
        },
    }
    if warmup is not None:
        result["warmup"] = warmup
    return result


def print_submission_result(
    *,
    status: str,
    results: list[dict[str, Any]],
    first_wrong: dict[str, Any] | None,
    wrong_dir: Path,
    run_id: str,
    run_dir: Path,
    display_root: Path,
) -> None:
    """Print the CLI result summary and artifact hints."""
    if status == "accepted":
        print(f"Accepted ({len(results)} case(s))")
        print(f"run: {rel(run_dir, display_root)}")
        return

    if first_wrong is None:
        return
    case_id = first_wrong["id"]
    print(f"{status.replace('_', ' ').title()} on case {case_id}")
    print(f"input:    {rel(wrong_dir / f'{case_id}.in', display_root)}")
    print(f"expected: {rel(wrong_dir / f'{case_id}.expected', display_root)}")
    print(f"actual:   {rel(wrong_dir / f'{case_id}.actual', display_root)}")
    print("")
    print("View:")
    print(f"  judge show {run_id} {case_id}")
