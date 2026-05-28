"""submission_result 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
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
    """copy_wrong_artifacts 함수를 실행하고 결과를 반환합니다.
    
    Args:
        wrong_dir (Path): `wrong_dir` 값입니다.
        case_id (str): `case_id` 값입니다.
        in_path (Path): `in_path` 값입니다.
        answer_path (Path): `answer_path` 값입니다.
        actual_path (Path): `actual_path` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
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
    """build_submission_result 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_id (str): `run_id` 값입니다.
        problem_id (str): 문제 ID입니다.
        profile (str): `profile` 값입니다.
        language (str): `language` 값입니다.
        status (str): `status` 값입니다.
        cases (list[dict[str, Any]]): `cases` 값입니다.
        max_time_ms (int): `max_time_ms` 값입니다.
        max_memory_bytes (int | None): `max_memory_bytes` 값입니다.
        warmup (dict[str, Any] | None): `warmup` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
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
    """print_submission_result 함수를 실행하고 결과를 반환합니다.
    
    Args:
        status (str): `status` 값입니다.
        results (list[dict[str, Any]]): `results` 값입니다.
        first_wrong (dict[str, Any] | None): `first_wrong` 값입니다.
        wrong_dir (Path): `wrong_dir` 값입니다.
        run_id (str): `run_id` 값입니다.
        run_dir (Path): `run_dir` 값입니다.
        display_root (Path): `display_root` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
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
