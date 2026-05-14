from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import cache_root, ensure_inside, rel, repo_root, validate_safe_id
from judge.utils.fs import path_size, read_json
from judge.utils.text import format_size


@dataclass
class CacheClearPlan:
    """Deletion plan for cache clear commands."""

    root: Path
    targets: list[Path]
    total_size: int
    operation_root: Path | None = None


def cache_status_data(root: Path | None = None) -> dict[str, object]:
    """Return a structured summary of generated datasets and run artifacts."""
    base = cache_root(root)
    problems = base / "problems"
    runs = base / "runs"
    problem_entries = []
    if problems.exists():
        for problem_dir in sorted(path for path in problems.iterdir() if path.is_dir()):
            caches = [path for path in problem_dir.iterdir() if path.is_dir()]
            problem_entries.append(
                {
                    "problemId": problem_dir.name,
                    "cacheCount": len(caches),
                    "size": path_size(problem_dir),
                }
            )
    run_entries = [path for path in runs.iterdir() if path.is_dir()] if runs.exists() else []
    return {
        "path": str(base),
        "exists": base.exists(),
        "totalSize": path_size(base),
        "problems": problem_entries,
        "runs": {"count": len(run_entries), "size": path_size(runs)},
    }


def cache_status(root: Path | None = None) -> None:
    """Print a summary of generated datasets and run artifacts."""
    base = cache_root(root)
    display_root = root or repo_root()
    problems = base / "problems"
    runs = base / "runs"
    print(f"cache: {rel(base, display_root)}")
    if not base.exists():
        print("status: empty")
        return
    total = path_size(base)
    print(f"total size: {format_size(total)}")
    if problems.exists():
        for problem_dir in sorted(path for path in problems.iterdir() if path.is_dir()):
            entries = [path for path in problem_dir.iterdir() if path.is_dir()]
            size = format_size(path_size(problem_dir))
            print(f"problem {problem_dir.name}: {len(entries)} cache(s), {size}")
    else:
        print("problem caches: 0")
    if runs.exists():
        entries = [path for path in runs.iterdir() if path.is_dir()]
        print(f"runs: {len(entries)} run(s), {format_size(path_size(runs))}")
    else:
        print("runs: 0")


def clear_targets(
    problem: str | None = None,
    profile: str | None = None,
    runs: bool = False,
    all_entries: bool = False,
    root: Path | None = None,
) -> list[Path]:
    """Resolve cache paths selected by clear command options."""
    base = cache_root(root)
    targets = []
    if problem:
        validate_safe_id("problem id", problem)
    if profile:
        validate_safe_id("profile", profile)
    if all_entries:
        targets.append(base)
    else:
        if problem:
            problem_base = base / "problems" / problem
            if profile:
                if problem_base.exists():
                    for cache_dir in problem_base.iterdir():
                        manifest = cache_dir / "manifest.json"
                        if manifest.exists():
                            try:
                                if read_json(manifest).get("profile") == profile:
                                    targets.append(cache_dir)
                            except json.JSONDecodeError:
                                continue
            else:
                targets.append(problem_base)
        if runs:
            targets.append(base / "runs")
    return [ensure_inside(path, base) for path in targets if path.exists()]


def build_cache_clear_plan(
    problem: str | None = None,
    profile: str | None = None,
    runs: bool = False,
    all_entries: bool = False,
    root: Path | None = None,
) -> CacheClearPlan:
    """Build a dry-run friendly plan for deleting cache paths."""
    targets = clear_targets(problem, profile, runs, all_entries, root)
    return CacheClearPlan(
        root=cache_root(root),
        targets=targets,
        total_size=sum(path_size(path) for path in targets),
        operation_root=root,
    )


def delete_cache_targets(targets: list[Path], root: Path | None = None) -> None:
    """Delete cache targets after validating they stay inside the cache root."""
    base = cache_root(root)
    display_root = root or repo_root()
    lock = base / ".lock"
    if lock.exists():
        raise JudgeError(f"cache is locked: {rel(lock, display_root)}")
    for path in targets:
        path = ensure_inside(path, base)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
