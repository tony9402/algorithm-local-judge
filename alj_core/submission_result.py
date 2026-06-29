"""제출 결과 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from alj_core.paths import rel


def copy_wrong_artifacts(
    wrong_dir: Path,
    case_id: str,
    in_path: Path,
    answer_path: Path,
    actual_path: Path,
) -> None:
    """오답 산출물 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        wrong_dir (Path): 오답 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        case_id (str): 입력, 출력, 오답 산출물을 구분하는 케이스 ID입니다.
        in_path (Path): in 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        answer_path (Path): 기준 솔루션이 생성한 정답 출력 파일입니다.
        actual_path (Path): 실제 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
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
    """제출 결과에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Args:
        run_id (str): 저장된 실행 결과와 산출물 디렉터리를 찾는 실행 ID입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        language (str): 제출 결과을 계산하거나 검증할 때 필요한 language 입력입니다.
        status (str): 제출 결과을 계산하거나 검증할 때 필요한 상태 입력입니다.
        cases (list[dict[str, Any]]): 제출 결과을 계산하거나 검증할 때 필요한 케이스 입력입니다.
        max_time_ms (int): 제출 결과을 계산하거나 검증할 때 필요한 max time ms 입력입니다.
        max_memory_bytes (int | None): 제출 결과을 계산하거나 검증할 때 필요한 max 메모리 바이트 입력입니다.
        warmup (dict[str, Any] | None): 제출 결과을 계산하거나 검증할 때 필요한 워밍업 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 제출 결과 데이터입니다.
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
