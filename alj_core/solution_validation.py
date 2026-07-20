"""솔루션 검증 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

from alj_core.compiler import compile_problem_tools
from alj_core.errors import JudgeError
from alj_core.generation import generate
from alj_core.paths import rel, repo_root
from alj_core.problem import tool_paths
from alj_core.solution_expectations import (
    EXPECTED_STATUS_BY_TOKEN,
    REFERENCE_SOLUTION,
    discover_solution_expectations,
    ensure_reference_solution,
    expected_status_from_solution_name,
    filter_solution_expectations,
    solution_path_key,
)
from alj_core.solution_models import (
    SolutionCheckResult,
    SolutionExpectation,
    SolutionVerificationResult,
)
from alj_core.submission import run_submission
from alj_core.utils.fs import read_json

SOLUTION_STATUS_RANKS = {
    "compile_error": 0,
    "accepted": 1,
    "ok": 1,
    "wrong_answer": 2,
    "time_limit": 3,
}
CASE_STATUS_ALIASES = {
    "ok": "accepted",
}
MAX_SOLUTION_WORKERS = 8


def solution_check_error(
    result: SolutionVerificationResult, root: Path | None = None
) -> JudgeError:
    failed = [check for check in result.checks if not check.passed]
    lines = [
        f"solution expectation check failed for problem {result.problem_id} "
        f"profile {result.profile}",
    ]
    for check in failed:
        lines.append(
            f"- {rel(check.source, root)}: expected {check.expected_status}, "
            f"got {check.actual_status}"
        )
        if check.message:
            lines.append(f"  {check.message}")
    return JudgeError("\n".join(lines))


def effective_solution_status(
    raw_status: str,
    cases: list[dict[str, Any]] | None,
) -> tuple[str, dict[str, Any]]:
    """케이스별 결과와 원본 run 상태를 요구사항의 기대 결과 우선순위로 집계합니다."""
    normalized_raw = str(raw_status or "unknown")
    case_counts: dict[str, int] = {}
    ranked_status = CASE_STATUS_ALIASES.get(normalized_raw, normalized_raw)
    if normalized_raw == "compile_error" or ranked_status not in SOLUTION_STATUS_RANKS:
        return (
            normalized_raw,
            {
                "rawStatus": normalized_raw,
                "rankedStatus": normalized_raw,
                "caseStatusCounts": case_counts,
            },
        )

    for item in cases or []:
        case_status = str(item.get("status") or "unknown")
        normalized_case = CASE_STATUS_ALIASES.get(case_status, case_status)
        case_counts[normalized_case] = case_counts.get(normalized_case, 0) + 1
        if normalized_case not in SOLUTION_STATUS_RANKS:
            continue
        if SOLUTION_STATUS_RANKS[normalized_case] > SOLUTION_STATUS_RANKS[ranked_status]:
            ranked_status = normalized_case

    return (
        ranked_status,
        {
            "rawStatus": normalized_raw,
            "rankedStatus": ranked_status,
            "caseStatusCounts": case_counts,
        },
    )


def solution_worker_count(solution_count: int, max_workers: int | None = None) -> int:
    if solution_count <= 1:
        return 1
    requested = max_workers if max_workers is not None else 1
    return max(1, min(MAX_SOLUTION_WORKERS, solution_count, requested))


def verify_problem_solutions(
    problem_id: str,
    profile: str = "hidden",
    root: Path | None = None,
    progress: Callable[[str], None] | None = None,
    raise_on_failure: bool = True,
    solution_paths: list[str] | None = None,
    warmup_profile: str | None = None,
    on_check: Callable[[SolutionCheckResult, int, int], None] | None = None,
    max_workers: int | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> SolutionVerificationResult:
    def emit(message: str) -> None:
        if progress is not None:
            progress(message)

    def check_cancelled() -> None:
        if cancel_check is not None:
            cancel_check()

    display_root = root or repo_root()
    check_cancelled()
    problem_dir, _, _, _ = tool_paths(problem_id, root)
    ensure_reference_solution(problem_id, root)
    all_expectations = discover_solution_expectations(problem_dir)
    expectations = filter_solution_expectations(
        all_expectations,
        problem_dir,
        solution_paths,
    )
    requested_subset = len(expectations) != len(all_expectations)
    if requested_subset:
        emit(f"Selected {len(expectations)}/{len(all_expectations)} solution(s) for verification.")
    check_cancelled()
    emit(f"Generating validation data for profile {profile}.")
    data_dir = generate(problem_id, profile, root=root, progress=progress)
    prepared_data_dirs = {profile: data_dir}
    if warmup_profile:
        check_cancelled()
        emit(f"Generating warmup data for profile {warmup_profile}.")
        prepared_data_dirs[warmup_profile] = generate(
            problem_id,
            warmup_profile,
            root=root,
            progress=progress,
        )

    checks = []
    total_expectations = len(expectations)
    worker_count = solution_worker_count(total_expectations, max_workers)
    prepared_tools = None
    if worker_count > 1:
        check_cancelled()
        emit(f"Preparing checker and problem tools once for {worker_count} worker(s).")
        prepared_tools = compile_problem_tools(problem_id, root, progress=progress)

    def run_check(expectation: SolutionExpectation) -> SolutionCheckResult:
        return _verify_solution_expectation(
            expectation,
            problem_id,
            profile,
            root,
            display_root,
            warmup_profile,
            prepared_data_dirs=prepared_data_dirs if worker_count > 1 else None,
            prepared_tools=prepared_tools,
        )

    if worker_count == 1:
        for index, expectation in enumerate(expectations, start=1):
            check_cancelled()
            emit(
                f"Verifying solution {rel(expectation.path, display_root)} "
                f"({index}/{total_expectations})."
            )
            check = run_check(expectation)
            check_cancelled()
            checks.append(check)
            if on_check is not None:
                on_check(check, index, total_expectations)
            check_cancelled()
    else:
        completed = 0
        expectations_iter = iter(expectations)
        pending = {}
        executor = ThreadPoolExecutor(max_workers=worker_count)
        interrupted = False

        def submit_next() -> bool:
            check_cancelled()
            try:
                expectation = next(expectations_iter)
            except StopIteration:
                return False
            pending[executor.submit(run_check, expectation)] = expectation
            return True

        try:
            for _ in range(worker_count):
                if not submit_next():
                    break
            while pending:
                done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                if not done:
                    check_cancelled()
                    continue
                for future in done:
                    pending.pop(future, None)
                    check_cancelled()
                    check = future.result()
                    checks.append(check)
                    completed += 1
                    emit(
                        f"Verified solution {rel(check.source, display_root)} "
                        f"({completed}/{total_expectations})."
                    )
                    if on_check is not None:
                        on_check(check, completed, total_expectations)
                    check_cancelled()
                    submit_next()
        except BaseException:
            interrupted = True
            for future in pending:
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=not interrupted, cancel_futures=interrupted)
        checks.sort(key=lambda check: solution_path_key(check.source))

    result = SolutionVerificationResult(
        problem_id,
        profile,
        checks,
        total_count=len(expectations) if requested_subset else len(all_expectations),
    )
    if raise_on_failure and not result.passed:
        raise solution_check_error(result, display_root)
    return result


def _verify_solution_expectation(
    expectation: SolutionExpectation,
    problem_id: str,
    profile: str,
    root: Path | None,
    display_root: Path,
    warmup_profile: str | None,
    prepared_data_dirs: dict[str, Path] | None = None,
    prepared_tools: dict[str, Path] | None = None,
) -> SolutionCheckResult:
    raw_actual_status = "compile_error"
    actual_status = "compile_error"
    run_id = None
    message = ""
    cases: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    status_evidence: dict[str, Any] = {}
    try:
        run_options: dict[str, Any] = {
            "root": root,
            "stop_on_first_failure": False,
        }
        if warmup_profile is not None:
            run_options["warmup_profile"] = warmup_profile
        if prepared_data_dirs is not None:
            run_options["prepared_data_dirs"] = prepared_data_dirs
        if prepared_tools is not None:
            run_options["prepared_tools"] = prepared_tools
        if expectation.language == "pypy":
            run_options["language"] = "pypy"
        run_dir = run_submission(
            expectation.path,
            problem_id,
            profile,
            **run_options,
        )
        result = read_json(run_dir / "result.json")
        raw_actual_status = str(result.get("status", "unknown"))
        run_id = result.get("runId")
        cases = list(result.get("cases") or [])
        metrics = dict(result.get("metrics") or {})
        actual_status, status_evidence = effective_solution_status(raw_actual_status, cases)
        if actual_status != expectation.status:
            message = f"run: {rel(run_dir, display_root)}"
            if raw_actual_status != actual_status:
                message += f"\nraw status: {raw_actual_status}"
    except JudgeError as exc:
        message = str(exc)
        status_evidence = {
            "rawStatus": raw_actual_status,
            "rankedStatus": actual_status,
            "caseStatusCounts": {},
        }
    return SolutionCheckResult(
        source=expectation.path,
        expected_status=expectation.status,
        actual_status=actual_status,
        run_id=run_id,
        passed=actual_status == expectation.status,
        message=message,
        cases=cases,
        metrics=metrics,
        raw_actual_status=raw_actual_status,
        status_evidence=status_evidence,
        language=expectation.language,
    )


_solution_path_key = solution_path_key
_filter_solution_expectations = filter_solution_expectations

__all__ = [
    "EXPECTED_STATUS_BY_TOKEN",
    "REFERENCE_SOLUTION",
    "SolutionCheckResult",
    "SolutionExpectation",
    "SolutionVerificationResult",
    "_filter_solution_expectations",
    "_solution_path_key",
    "discover_solution_expectations",
    "effective_solution_status",
    "ensure_reference_solution",
    "expected_status_from_solution_name",
    "filter_solution_expectations",
    "solution_check_error",
    "solution_worker_count",
    "solution_path_key",
    "verify_problem_solutions",
]
