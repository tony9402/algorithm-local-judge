from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge.core.compiler import SUPPORTED_USER_SUFFIXES
from judge.core.errors import JudgeError
from judge.core.generation import generate
from judge.core.paths import rel, repo_root
from judge.core.problem import tool_paths
from judge.core.submission import run_submission
from judge.utils.fs import read_json

REFERENCE_SOLUTION = "main_solution.ac.cpp"
EXPECTED_STATUS_BY_TOKEN = {
    "ac": "accepted",
    "wa": "wrong_answer",
    "tle": "time_limit",
    "mle": "memory_limit",
}


@dataclass(frozen=True)
class SolutionExpectation:
    """One solution source file and the status it is expected to produce."""

    path: Path
    token: str
    status: str


@dataclass(frozen=True)
class SolutionCheckResult:
    """Observed result for one expected solution run."""

    source: Path
    expected_status: str
    actual_status: str
    run_id: str | None
    passed: bool
    message: str = ""
    cases: list[dict[str, Any]] | None = None
    metrics: dict[str, Any] | None = None

    def to_dict(self, root: Path | None = None) -> dict[str, object]:
        """Return a compact serializable representation for CLI/reporting."""
        return {
            "source": rel(self.source, root),
            "expectedStatus": self.expected_status,
            "actualStatus": self.actual_status,
            "runId": self.run_id,
            "passed": self.passed,
            "message": self.message,
            "cases": self.cases or [],
            "metrics": self.metrics or {},
        }


@dataclass(frozen=True)
class SolutionVerificationResult:
    """Aggregate result for solution expectation verification."""

    problem_id: str
    profile: str
    checks: list[SolutionCheckResult]
    total_count: int | None = None

    @property
    def passed(self) -> bool:
        """Return whether every discovered solution matched its expected status."""
        return all(check.passed for check in self.checks)

    def to_dict(self, root: Path | None = None) -> dict[str, object]:
        """Return a compact serializable representation for pack build output."""
        return {
            "problemId": self.problem_id,
            "profile": self.profile,
            "passed": self.passed,
            "verifiedCount": len(self.checks),
            "totalCount": self.total_count if self.total_count is not None else len(self.checks),
            "skippedCount": max(
                0,
                (self.total_count if self.total_count is not None else len(self.checks))
                - len(self.checks),
            ),
            "checks": [check.to_dict(root) for check in self.checks],
        }


def expected_status_from_solution_name(path: Path) -> tuple[str, str]:
    """Return the expectation token and judge status encoded in a solution filename."""
    parts = path.name.split(".")
    if len(parts) < 3:
        raise JudgeError(
            f"solution filename must include expected result token: {path.name} "
            "(example: solution.wa.cpp)"
        )
    token = parts[-2].lower()
    try:
        return token, EXPECTED_STATUS_BY_TOKEN[token]
    except KeyError as exc:
        allowed = ", ".join(sorted(EXPECTED_STATUS_BY_TOKEN))
        raise JudgeError(
            f"unsupported expected result token in {path.name}: {token} "
            f"(allowed: {allowed})"
        ) from exc


def discover_solution_expectations(problem_dir: Path) -> list[SolutionExpectation]:
    """Discover all supported solution source files and their expected statuses."""
    solutions_dir = problem_dir / "solutions"
    if not solutions_dir.exists():
        raise JudgeError(f"solutions directory not found: {solutions_dir}")
    expectations = []
    for source in sorted(path for path in solutions_dir.rglob("*") if path.is_file()):
        if source.suffix.lower() not in SUPPORTED_USER_SUFFIXES:
            continue
        token, status = expected_status_from_solution_name(source)
        expectations.append(SolutionExpectation(source, token, status))
    if not expectations:
        raise JudgeError(f"no expected solution files found under {solutions_dir}")
    return expectations


def ensure_reference_solution(problem_id: str, root: Path | None = None) -> Path:
    """Ensure answer data is generated from solutions/main_solution.ac.cpp."""
    problem_dir, _, _, paths = tool_paths(problem_id, root)
    reference = problem_dir / "solutions" / REFERENCE_SOLUTION
    if not reference.exists():
        raise JudgeError(f"reference solution not found: {rel(reference, root)}")
    if paths["solution"].resolve() != reference.resolve():
        raise JudgeError(
            "problem.json tools.solution must point to "
            f"solutions/{REFERENCE_SOLUTION}; got {rel(paths['solution'], root)}"
        )
    return reference


def _solution_path_key(path: Path | str) -> str:
    """Normalize a solution path request for matching discovered files."""
    raw = str(path).replace("\\", "/").strip().lstrip("./")
    parts = [part for part in raw.split("/") if part and part != "."]
    if "solutions" in parts:
        parts = parts[parts.index("solutions") :]
    elif parts:
        parts = ["solutions", *parts]
    return "/".join(parts)


def _filter_solution_expectations(
    expectations: list[SolutionExpectation],
    problem_dir: Path,
    requested_paths: list[str] | None,
) -> list[SolutionExpectation]:
    """Return only requested solution expectations, preserving discovery order."""
    if not requested_paths:
        return expectations
    requested = {_solution_path_key(path) for path in requested_paths if str(path).strip()}
    if not requested:
        return expectations
    by_key = {rel(expectation.path, problem_dir): expectation for expectation in expectations}
    missing = sorted(requested - set(by_key))
    if missing:
        available = ", ".join(sorted(by_key)) or "none"
        raise JudgeError(
            f"unknown solution file(s): {', '.join(missing)} "
            f"(available: {available})"
        )
    return [
        expectation
        for expectation in expectations
        if rel(expectation.path, problem_dir) in requested
    ]


def solution_check_error(
    result: SolutionVerificationResult, root: Path | None = None
) -> JudgeError:
    """Build a readable verification failure error."""
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
    """Run every expected solution against the profile and validate its status."""

    def emit(message: str) -> None:
        if progress is not None:
            progress(message)

    display_root = root or repo_root()
    problem_dir, _, _, _ = tool_paths(problem_id, root)
    ensure_reference_solution(problem_id, root)
    all_expectations = discover_solution_expectations(problem_dir)
    expectations = _filter_solution_expectations(
        all_expectations,
        problem_dir,
        solution_paths,
    )
    requested_subset = len(expectations) != len(all_expectations)
    if len(expectations) != len(all_expectations):
        emit(f"Selected {len(expectations)}/{len(all_expectations)} solution(s) for verification.")
    emit(f"Generating validation data for profile {profile}.")
    generate(problem_id, profile, root=root, progress=progress)

    checks = []
    for index, expectation in enumerate(expectations, start=1):
        emit(
            f"Verifying solution {rel(expectation.path, display_root)} "
            f"({index}/{len(expectations)})."
        )
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
        checks.append(
            SolutionCheckResult(
                source=expectation.path,
                expected_status=expectation.status,
                actual_status=actual_status,
                run_id=run_id,
                passed=actual_status == expectation.status,
                message=message,
                cases=cases,
                metrics=metrics,
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
