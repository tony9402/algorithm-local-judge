from __future__ import annotations

from pathlib import Path

from judge.core.compiler import SUPPORTED_USER_SUFFIXES
from judge.core.errors import JudgeError
from judge.core.paths import rel
from judge.core.problem import tool_paths
from judge.core.solution_models import SolutionExpectation

REFERENCE_SOLUTION = "main_solution.ac.cpp"
EXPECTED_STATUS_BY_TOKEN = {
    "ac": "accepted",
    "wa": "wrong_answer",
    "tle": "time_limit",
    "mle": "memory_limit",
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
            f"unsupported expected result token in {path.name}: {token} (allowed: {allowed})"
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


def solution_path_key(path: Path | str) -> str:
    """Normalize a solution path request for matching discovered files."""
    raw = str(path).replace("\\", "/").strip().lstrip("./")
    parts = [part for part in raw.split("/") if part and part != "."]
    if "solutions" in parts:
        parts = parts[parts.index("solutions") :]
    elif parts:
        parts = ["solutions", *parts]
    return "/".join(parts)


def filter_solution_expectations(
    expectations: list[SolutionExpectation],
    problem_dir: Path,
    requested_paths: list[str] | None,
) -> list[SolutionExpectation]:
    """Return only requested solution expectations, preserving discovery order."""
    if not requested_paths:
        return expectations
    requested = {solution_path_key(path) for path in requested_paths if str(path).strip()}
    if not requested:
        return expectations
    by_key = {rel(expectation.path, problem_dir): expectation for expectation in expectations}
    missing = sorted(requested - set(by_key))
    if missing:
        available = ", ".join(sorted(by_key)) or "none"
        raise JudgeError(
            f"unknown solution file(s): {', '.join(missing)} (available: {available})"
        )
    return [
        expectation
        for expectation in expectations
        if rel(expectation.path, problem_dir) in requested
    ]
