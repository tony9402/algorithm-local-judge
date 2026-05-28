"""solution_validation 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.generation import generate
from judge.core.paths import rel, repo_root
from judge.core.problem import tool_paths
from judge.core.solution_expectations import (
    EXPECTED_STATUS_BY_TOKEN,
    REFERENCE_SOLUTION,
    discover_solution_expectations,
    ensure_reference_solution,
    expected_status_from_solution_name,
    filter_solution_expectations,
    solution_path_key,
)
from judge.core.solution_models import (
    SolutionCheckResult,
    SolutionExpectation,
    SolutionVerificationResult,
)
from judge.core.submission import run_submission
from judge.utils.fs import read_json


def solution_check_error(
    result: SolutionVerificationResult, root: Path | None = None
) -> JudgeError:
    """solution_check_error 함수를 실행하고 결과를 반환합니다.
    
    Args:
        result (SolutionVerificationResult): `result` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        JudgeError: 처리 결과를 반환합니다.
    """
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


def verify_problem_solutions(
    problem_id: str,
    profile: str = "hidden",
    root: Path | None = None,
    progress: Callable[[str], None] | None = None,
    raise_on_failure: bool = True,
    solution_paths: list[str] | None = None,
    warmup_profile: str | None = None,
) -> SolutionVerificationResult:
    """verify_problem_solutions 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str): `profile` 값입니다.
        root (Path | None): `root` 값입니다.
        progress (Callable[[str], None] | None): `progress` 값입니다.
        raise_on_failure (bool): `raise_on_failure` 값입니다.
        solution_paths (list[str] | None): `solution_paths` 값입니다.
        warmup_profile (str | None): `warmup_profile` 값입니다.
    
    Returns:
        SolutionVerificationResult: 처리 결과를 반환합니다.
    """

    def emit(message: str) -> None:
    """emit 함수를 실행하고 결과를 반환합니다.
    
    Args:
        message (str): 메시지입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
        if progress is not None:
            progress(message)

    display_root = root or repo_root()
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
    emit(f"Generating validation data for profile {profile}.")
    generate(problem_id, profile, root=root, progress=progress)

    checks = []
    for index, expectation in enumerate(expectations, start=1):
        emit(
            f"Verifying solution {rel(expectation.path, display_root)} "
            f"({index}/{len(expectations)})."
        )
        checks.append(
            _verify_solution_expectation(
                expectation,
                problem_id,
                profile,
                root,
                display_root,
                warmup_profile,
            )
        )

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
) -> SolutionCheckResult:
    """_verify_solution_expectation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        expectation (SolutionExpectation): `expectation` 값입니다.
        problem_id (str): 문제 ID입니다.
        profile (str): `profile` 값입니다.
        root (Path | None): `root` 값입니다.
        display_root (Path): `display_root` 값입니다.
        warmup_profile (str | None): `warmup_profile` 값입니다.
    
    Returns:
        SolutionCheckResult: 처리 결과를 반환합니다.
    """
    actual_status = "compile_error"
    run_id = None
    message = ""
    cases: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    try:
        run_options: dict[str, Any] = {
            "root": root,
            "stop_on_first_failure": False,
        }
        if warmup_profile is not None:
            run_options["warmup_profile"] = warmup_profile
        run_dir = run_submission(
            expectation.path,
            problem_id,
            profile,
            **run_options,
        )
        result = read_json(run_dir / "result.json")
        actual_status = str(result.get("status", "unknown"))
        run_id = result.get("runId")
        cases = list(result.get("cases") or [])
        metrics = dict(result.get("metrics") or {})
        if actual_status != expectation.status:
            message = f"run: {rel(run_dir, display_root)}"
    except JudgeError as exc:
        message = str(exc)
    return SolutionCheckResult(
        source=expectation.path,
        expected_status=expectation.status,
        actual_status=actual_status,
        run_id=run_id,
        passed=actual_status == expectation.status,
        message=message,
        cases=cases,
        metrics=metrics,
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
    "ensure_reference_solution",
    "expected_status_from_solution_name",
    "filter_solution_expectations",
    "solution_check_error",
    "solution_path_key",
    "verify_problem_solutions",
]
