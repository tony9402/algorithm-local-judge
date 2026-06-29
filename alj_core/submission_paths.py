"""제출 경로 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from alj_core.errors import JudgeError
from alj_core.generation import cache_dir_for
from alj_core.manifest import generation_key, validate_manifest
from alj_core.paths import cache_root, repo_root
from alj_core.problem_discovery import problem_roots


def new_run_dir(root: Path | None = None) -> tuple[str, Path]:
    """new 실행 dir 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.

    Returns:
        tuple[str, Path]: 검증된 new 실행 dir 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = cache_root(root) / "runs" / run_id
    suffix = 1
    while candidate.exists():
        candidate = cache_root(root) / "runs" / f"{run_id}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate.name, candidate


def infer_problem_id(
    source: Path, explicit_problem: str | None = None, root: Path | None = None
) -> str:
    root = root or repo_root()
    source = source.resolve()
    inferred = None
    roots = sorted(
        (problems_dir.resolve() for problems_dir in problem_roots(root)),
        key=lambda problems_dir: len(problems_dir.parts),
        reverse=True,
    )
    for problems_dir in roots:
        try:
            relative = source.relative_to(problems_dir)
            if relative.parts:
                inferred = relative.parts[0]
                break
        except ValueError:
            continue
    cwd = Path.cwd().resolve()
    if inferred is None:
        for problems_dir in roots:
            try:
                relative = cwd.relative_to(problems_dir)
                if relative.parts:
                    inferred = relative.parts[0]
                    break
            except ValueError:
                continue
    if explicit_problem and inferred and explicit_problem != inferred:
        raise JudgeError(
            f"problem mismatch: --problem {explicit_problem}, path suggests {inferred}"
        )
    if explicit_problem:
        return explicit_problem
    if inferred:
        return inferred
    raise JudgeError(
        "could not infer problem id. Use:\n"
        f"  python3 -m judge --problem 06 {source}\n"
        f"  python3 -m judge run --problem 06 {source}"
    )


def latest_cache_for(problem_id: str, profile: str, root: Path | None = None) -> Path | None:
    key = generation_key(problem_id, profile, root)
    candidate = cache_dir_for(problem_id, key, root)
    if validate_manifest(candidate, problem_id, profile, key):
        return candidate
    return None
