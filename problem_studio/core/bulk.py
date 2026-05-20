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
from judge.core.problem import discover_problem_ids
from problem_studio.core.packflow import build_problem_pack_bundle, verify_solutions
from problem_studio.core.validation import validate_all_data

DEFAULT_MAX_WORKERS = 4


def bulk_worker_count(problem_count: int, requested: int | None = None) -> int:
    """Return a bounded parallel worker count for workspace-wide builds."""
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
) -> dict[str, Any]:
    """Run the same full-test stages used before building one problem pack."""
    progress("Checking cases.yml.")
    cases_result = compile_problem_cases(problem_id, None, workspace)
    if not cases_result.valid:
        raise JudgeError("cases.yml compile failed\n\n" + format_compile_result(cases_result))

    progress("Compiling tools.")
    tools = compile_problem_tools(problem_id, workspace)

    progress("Generating and validating all data.")
    validation = validate_all_data(workspace, problem_id, force, progress, cases_result)

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
            summary
            if not failed_checks
            else f"{len(failed_checks)}개 솔루션 기대 결과 불일치"
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
) -> dict[str, Any]:
    """Full-test selected problems and build one source-free pack containing them."""
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
        if progress:
            progress(f"[{index}/{len(selected_problem_ids)}] Problem {problem_id}: {message}")

    def run_one(index: int, problem_id: str) -> dict[str, Any]:
        try:
            emit(index, problem_id, "Starting full test.")
            test_result = run_problem_full_test(
                workspace,
                problem_id,
                verify_profile,
                force,
                lambda message, i=index, pid=problem_id: emit(i, pid, message),
            )
            if not test_result["passed"]:
                emit(index, problem_id, f"Full test failed: {test_result['summary']}")
                return {**test_result, "pack": None}

            emit(index, problem_id, "Full test passed.")
            return {**test_result, "pack": None}
        except Exception as exc:
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
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(run_one, index, problem_id): index
            for index, problem_id in enumerate(selected_problem_ids, start=1)
        }
        for future in as_completed(futures):
            results_by_index[futures[future]] = future.result()

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
        pack = build_problem_pack_bundle(
            workspace,
            selected_problem_ids,
            pack_id,
            output_dir,
            platform_id,
            verify_profile,
            solution_checks=solution_checks,
        )
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
