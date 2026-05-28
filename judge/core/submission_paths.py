from __future__ import annotations

from datetime import datetime
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.generation import cache_dir_for
from judge.core.manifest import generation_key, validate_manifest
from judge.core.paths import cache_root, repo_root
from judge.core.problem_discovery import problem_roots


def new_run_dir(root: Path | None = None) -> tuple[str, Path]:
    """Create and return a unique run artifact directory."""
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
    """Infer a problem id from source path, cwd, or an explicit option."""
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
    """Return the current valid cache directory for a problem/profile."""
    key = generation_key(problem_id, profile, root)
    candidate = cache_dir_for(problem_id, key, root)
    if validate_manifest(candidate, problem_id, profile, key):
        return candidate
    return None
