"""솔루션 기대 상태 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
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
    """설정과 디렉터리를 탐색해 사용 가능한 솔루션 기대 상태 항목을 찾습니다.

    Args:
        problem_dir (Path): 문제의 소스, 도구, 설정 파일이 들어 있는 디렉터리입니다.

    Returns:
        list[SolutionExpectation]: 호출자가 순회하거나 화면에 표시할 솔루션 기대 상태 항목 목록입니다.
    """
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
    """참조 솔루션 조건을 확인하고 위반 시 호출자가 중단할 수 있는 예외를 발생시킵니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.

    Returns:
        Path: 검증된 참조 솔루션 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
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
