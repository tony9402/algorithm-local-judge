"""bulk 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from judge.core.cases_compile import compile_problem_cases, format_compile_result
from judge.core.compiler import compile_problem_tools
from judge.core.errors import JudgeError
from judge.core.paths import validate_safe_id
from problem_studio.core.packflow import build_problem_pack_bundle, verify_solutions
from problem_studio.core.validation import validate_all_data
from problem_studio.core.workspace import (
    discover_workspace_problem_ids as discover_problem_ids,
)

DEFAULT_MAX_WORKERS = 4


def check_cancel(cancel_token: Any | None) -> None:
    """check_cancel 함수를 실행하고 결과를 반환합니다.
    
    Args:
        cancel_token (Any | None): `cancel_token` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    if cancel_token:
        cancel_token.check()


def cancellation_requested(cancel_token: Any | None) -> bool:
    """cancellation_requested 함수를 실행하고 결과를 반환합니다.
    
    Args:
        cancel_token (Any | None): `cancel_token` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    return bool(getattr(cancel_token, "cancelled", False))


def bulk_worker_count(problem_count: int, requested: int | None = None) -> int:
    """bulk_worker_count 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_count (int): `problem_count` 값입니다.
        requested (int | None): `requested` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
    if problem_count <= 0:
        return 1
    if requested is not None and requested > 0:
        return max(1, min(problem_count, requested))
    cpu_count = os.cpu_count() or 1
    return max(1, min(problem_count, cpu_count, DEFAULT_MAX_WORKERS))


def run_problem_full_test(
    workspace: Path,
    problem_id: str,
    verify_profile: str,
    force: bool,
    progress: Callable[[str], None],
    cancel_token: Any | None = None,
) -> dict[str, Any]:
    """run_problem_full_test 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        verify_profile (str): `verify_profile` 값입니다.
        force (bool): `force` 값입니다.
        progress (Callable[[str], None]): `progress` 값입니다.
        cancel_token (Any | None): `cancel_token` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    check_cancel(cancel_token)
    progress("Checking cases.yml.")
    cases_result = compile_problem_cases(problem_id, None, workspace)
    if not cases_result.valid:
        raise JudgeError("cases.yml compile failed\n\n" + format_compile_result(cases_result))

    check_cancel(cancel_token)
    progress("Compiling tools.")
    tools = compile_problem_tools(problem_id, workspace)

    check_cancel(cancel_token)
    progress("Generating and validating all data.")
    validation = validate_all_data(workspace, problem_id, force, progress, cases_result)

    check_cancel(cancel_token)
    progress("Verifying expected solution results.")
    verification = verify_solutions(
        workspace,
        problem_id,
        verify_profile,
        progress=progress,
        raise_on_failure=False,
    )
    failed_checks = [check for check in verification.get("checks", []) if not check.get("passed")]
    summary = (
        f"{len(cases_result.profiles)} profile 확인 · "
        f"{len(tools)}개 도구 컴파일 · "
        f"{validation['caseCount']}개 데이터 검증 · "
        f"{len(verification.get('checks', []))}개 솔루션 검증"
    )
    return {
        "problemId": problem_id,
        "passed": not failed_checks,
        "summary": (
            summary if not failed_checks else f"{len(failed_checks)}개 솔루션 기대 결과 불일치"
        ),
        "profiles": [profile.name for profile in cases_result.profiles],
        "toolCount": len(tools),
        "validation": validation,
        "solutionVerification": verification,
    }


def build_all_problem_packs(
    workspace: Path,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    force: bool = False,
    progress: Callable[[str], None] | None = None,
    max_workers: int | None = None,
    problem_ids: list[str] | None = None,
    cancel_token: Any | None = None,
) -> dict[str, Any]:
    """build_all_problem_packs 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        pack_id (str): `pack_id` 값입니다.
        output_dir (Path): `output_dir` 값입니다.
        platform_id (str | None): `platform_id` 값입니다.
        verify_profile (str): `verify_profile` 값입니다.
        force (bool): `force` 값입니다.
        progress (Callable[[str], None] | None): `progress` 값입니다.
        max_workers (int | None): `max_workers` 값입니다.
        problem_ids (list[str] | None): `problem_ids` 값입니다.
        cancel_token (Any | None): `cancel_token` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    check_cancel(cancel_token)
    available_problem_ids = discover_problem_ids(workspace)
    if problem_ids is None:
        selected_problem_ids = available_problem_ids
    else:
        selected_problem_ids = []
        for problem_id in problem_ids:
            validate_safe_id("problem id", problem_id)
            if problem_id not in selected_problem_ids:
                selected_problem_ids.append(problem_id)
        unknown = sorted(set(selected_problem_ids) - set(available_problem_ids))
        if unknown:
            raise JudgeError(f"unknown problem id(s): {', '.join(unknown)}")
    if not selected_problem_ids:
        raise JudgeError("no problems found")
    worker_count = bulk_worker_count(len(selected_problem_ids), max_workers)

    def emit(index: int, problem_id: str, message: str) -> None:
    """emit 함수를 실행하고 결과를 반환합니다.
    
    Args:
        index (int): `index` 값입니다.
        problem_id (str): 문제 ID입니다.
        message (str): 메시지입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
        check_cancel(cancel_token)
        if progress:
            progress(f"[{index}/{len(selected_problem_ids)}] Problem {problem_id}: {message}")

    def run_one(index: int, problem_id: str) -> dict[str, Any]:
    """run_one 함수를 실행하고 결과를 반환합니다.
    
    Args:
        index (int): `index` 값입니다.
        problem_id (str): 문제 ID입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
        try:
            check_cancel(cancel_token)
            emit(index, problem_id, "Starting full test.")
            test_result = run_problem_full_test(
                workspace,
                problem_id,
                verify_profile,
                force,
                lambda message, i=index, pid=problem_id: emit(i, pid, message),
                cancel_token=cancel_token,
            )
            check_cancel(cancel_token)
            if not test_result["passed"]:
                emit(index, problem_id, f"Full test failed: {test_result['summary']}")
                return {**test_result, "pack": None}

            emit(index, problem_id, "Full test passed.")
            return {**test_result, "pack": None}
        except Exception as exc:
            if cancellation_requested(cancel_token):
                check_cancel(cancel_token)
            emit(index, problem_id, f"Failed: {exc}")
            return {
                "problemId": problem_id,
                "passed": False,
                "summary": str(exc),
                "pack": None,
            }

    if progress:
        progress(f"Running {len(selected_problem_ids)} problems with {worker_count} worker(s).")
    results_by_index: dict[int, dict[str, Any]] = {}
    executor = ThreadPoolExecutor(max_workers=worker_count)
    futures = {}
    try:
        futures = {
            executor.submit(run_one, index, problem_id): index
            for index, problem_id in enumerate(selected_problem_ids, start=1)
        }
        for future in as_completed(futures):
            check_cancel(cancel_token)
            results_by_index[futures[future]] = future.result()
            check_cancel(cancel_token)
    finally:
        if cancellation_requested(cancel_token):
            for future in futures:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
        else:
            executor.shutdown(wait=True)

    results = [results_by_index[index] for index in range(1, len(selected_problem_ids) + 1)]
    failed = [item for item in results if not item["passed"]]
    pack = None
    if not failed:
        solution_checks = [
            check
            for item in results
            for check in item.get("solutionVerification", {}).get("checks", [])
        ]
        if progress:
            progress(
                f"Building pack {pack_id} with {len(selected_problem_ids)} selected problem(s)."
            )
        check_cancel(cancel_token)
        pack = build_problem_pack_bundle(
            workspace,
            selected_problem_ids,
            pack_id,
            output_dir,
            platform_id,
            verify_profile,
            solution_checks=solution_checks,
        )
        check_cancel(cancel_token)
        if progress:
            progress(f"Pack built: {pack['archiveLabel']}")
        results = [{**item, "pack": pack} for item in results]
    return {
        "passed": not failed,
        "problemCount": len(selected_problem_ids),
        "parallelWorkers": worker_count,
        "packCount": 1 if pack else 0,
        "packId": pack_id,
        "outputDir": str(output_dir),
        "problems": results,
        "packs": [pack] if pack else [],
        "pack": pack,
        "failedCount": len(failed),
        "summary": (
            f"{len(selected_problem_ids)}개 문제 테스트 통과 · 1개 팩 생성"
            if not failed
            else f"{len(selected_problem_ids)}개 중 {len(failed)}개 문제 실패 · 팩 생성 안 함"
        ),
    }
