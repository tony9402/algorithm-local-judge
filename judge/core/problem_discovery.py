"""problem_discovery 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.paths import (
    problem_pack_root,
    problem_source_root,
    rel,
    repo_root,
    validate_safe_id,
)


def installed_problem_roots() -> list[Path]:
    """installed_problem_roots 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        list[Path]: 처리 결과를 반환합니다.
    """
    packs_root = problem_pack_root()
    if not packs_root.exists():
        return []
    return [
        pack_dir / "problems"
        for pack_dir in sorted(path for path in packs_root.iterdir() if path.is_dir())
        if (pack_dir / "problems").exists()
    ]


def installed_source_problem_roots() -> list[Path]:
    """installed_source_problem_roots 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        list[Path]: 처리 결과를 반환합니다.
    """
    sources_root = problem_source_root()
    if not sources_root.exists():
        return []
    return [
        problems_dir
        for problems_dir in sorted(sources_root.glob("*/*/problems"))
        if problems_dir.is_dir()
    ]


def workspace_problem_roots(root: Path) -> list[Path]:
    """workspace_problem_roots 함수를 실행하고 결과를 반환합니다.
    
    Args:
        root (Path): `root` 값입니다.
    
    Returns:
        list[Path]: 처리 결과를 반환합니다.
    """
    container = root / "problems"
    roots = []
    if container.exists():
        roots.extend(
            child / "problems"
            for child in sorted(path for path in container.iterdir() if path.is_dir())
            if (child / "problems").is_dir()
        )
    roots.append(container)
    return roots


def problem_roots(root: Path | None = None) -> list[Path]:
    """problem_roots 함수를 실행하고 결과를 반환합니다.
    
    Args:
        root (Path | None): `root` 값입니다.
    
    Returns:
        list[Path]: 처리 결과를 반환합니다.
    """
    if root is not None:
        return workspace_problem_roots(root)
    roots = []
    roots.extend(workspace_problem_roots(repo_root()))
    roots.extend(installed_problem_roots())
    roots.extend(installed_source_problem_roots())
    return roots


def problem_workspace_root(problem_dir: Path, root: Path | None = None) -> Path:
    """problem_workspace_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_dir (Path): `problem_dir` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if root is not None:
        return root
    if problem_dir.parent.name == "problems":
        return problem_dir.parent.parent
    return repo_root()


def find_problem_dir(problem_id: str, root: Path | None = None) -> Path:
    """find_problem_dir 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    validate_safe_id("problem id", problem_id)
    base = root or repo_root()
    direct_problem_dir = base / "problems" / problem_id
    if (direct_problem_dir / "problem.json").exists():
        return direct_problem_dir
    for problems_dir in problem_roots(root):
        problem_dir = problems_dir / problem_id
        if (problem_dir / "problem.json").exists():
            return problem_dir
    raise JudgeError(f"problem metadata not found: {rel(base / 'problems' / problem_id)}")


def problem_sort_key(problem_id: str) -> tuple[Any, ...]:
    """problem_sort_key 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
    
    Returns:
        tuple[Any, ...]: 처리 결과를 반환합니다.
    """
    if problem_id.isdigit():
        return (0, int(problem_id), problem_id)
    return (1, problem_id)


def discover_problem_ids(root: Path | None = None) -> list[str]:
    """discover_problem_ids 함수를 실행하고 결과를 반환합니다.
    
    Args:
        root (Path | None): `root` 값입니다.
    
    Returns:
        list[str]: 처리 결과를 반환합니다.
    """
    problem_ids = set()
    for problems_dir in problem_roots(root):
        if not problems_dir.exists():
            continue
        problem_ids.update(path.parent.name for path in problems_dir.glob("*/problem.json"))
    return sorted(problem_ids, key=problem_sort_key)


def validate_problem_sequence(problem_ids: list[str]) -> list[str]:
    """validate_problem_sequence 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_ids (list[str]): `problem_ids` 값입니다.
    
    Returns:
        list[str]: 처리 결과를 반환합니다.
    """
    errors = []
    if not problem_ids:
        return ["no problems found"]

    numbers = []
    seen = {}
    for problem_id in problem_ids:
        if not problem_id.isdigit():
            errors.append(f"problem id must be numeric: {problem_id}")
            continue
        number = int(problem_id)
        numbers.append(number)
        seen.setdefault(number, []).append(problem_id)

    for number, ids in sorted(seen.items()):
        if len(ids) > 1:
            errors.append(f"duplicate numeric problem id {number}: {', '.join(ids)}")

    if numbers:
        expected = set(range(1, max(numbers) + 1))
        actual = set(numbers)
        missing = sorted(expected - actual)
        if 1 not in actual:
            errors.append("problem numbering must start at 1")
        if missing:
            errors.append(
                "missing problem number(s): " + ", ".join(str(number) for number in missing)
            )

    return errors
