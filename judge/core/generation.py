from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from commons.generate import generate_cases
from judge.core.cases_compile import ensure_cases_compiled
from judge.core.compiler import compile_problem_tools
from judge.core.errors import JudgeError
from judge.core.manifest import build_manifest, generation_key, source_hashes, validate_manifest
from judge.core.paths import cache_root, rel, repo_root, validate_safe_id
from judge.core.problem import tool_paths
from judge.core.runner import checker_compare, solution_write, validator_check
from judge.utils.fs import write_json


def cache_dir_for(problem_id: str, key: str, root: Path | None = None) -> Path:
    """Return the cache directory for a problem and generation key."""
    return cache_root(root) / "problems" / problem_id / key


def acquire_generation_lock(
    problem_id: str,
    profile: str,
    key: str,
    root: Path | None = None,
    timeout_seconds: int = 30,
) -> Path:
    """Acquire a filesystem lock for one generation job."""
    display_root = root or repo_root()
    locks_dir = cache_root(root) / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    lock_dir = locks_dir / f"{problem_id}-{profile}-{key}.lock"
    deadline = time.time() + timeout_seconds
    while True:
        try:
            lock_dir.mkdir()
            return lock_dir
        except FileExistsError:
            if time.time() >= deadline:
                raise JudgeError(
                    f"timed out waiting for generation lock: {rel(lock_dir, display_root)}"
                ) from None
            time.sleep(0.1)


def generate(
    problem_id: str,
    profile: str | None = None,
    force: bool = False,
    root: Path | None = None,
    verbose: bool = False,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Generate or reuse test data for a problem/profile pair."""

    def emit(message: str) -> None:
        if progress is not None:
            progress(message)

    display_root = root or repo_root()
    _, _, metadata, paths = tool_paths(problem_id, root)
    profile = profile or metadata.get("defaultProfile", "full")
    validate_safe_id("profile", profile)
    emit(f"Compiling cases.yml for profile {profile}.")
    ensure_cases_compiled(problem_id, profile, root)
    emit(f"Preparing generator tools for problem {problem_id}.")
    outputs = compile_problem_tools(problem_id, root, progress=progress)
    key = generation_key(problem_id, profile, root)
    final_dir = cache_dir_for(problem_id, key, root)
    if final_dir.exists() and validate_manifest(final_dir, problem_id, profile, key) and not force:
        emit(f"Using cached data at {rel(final_dir, display_root)}.")
        print(f"Using cached data: {rel(final_dir, display_root)}")
        return final_dir

    lock_dir = acquire_generation_lock(problem_id, profile, key, root)
    if final_dir.exists() and validate_manifest(final_dir, problem_id, profile, key) and not force:
        shutil.rmtree(lock_dir)
        emit(f"Using cached data at {rel(final_dir, display_root)}.")
        print(f"Using cached data: {rel(final_dir, display_root)}")
        return final_dir

    operation_id = f"generate-{problem_id}-{os.getpid()}-{int(time.time() * 1000)}"
    tmp_dir = cache_root(root) / "tmp" / operation_id
    cases_dir = tmp_dir / "cases"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        limits = metadata.get("limits", {})
        try:
            emit(f"Generating input cases for profile {profile}.")
            summary = generate_cases(
                paths["generatorConfig"],
                outputs["generator"],
                cases_dir,
                profile,
            )
        except Exception as exc:
            raise JudgeError(f"generator script failed: {exc}") from exc

        case_summaries = summary.get("cases", [])
        if not case_summaries:
            raise JudgeError("generator script produced no cases")

        for index, in_path in enumerate(sorted(cases_dir.glob("*.in")), start=1):
            emit(f"Validating generated case {in_path.stem} ({index}/{len(case_summaries)}).")
            validator_check(
                outputs["validator"],
                in_path,
                limits.get("generationTimeoutMs", 5000),
                profile=profile,
                case_index=index,
                case_total=len(case_summaries),
                root=display_root,
            )
            answer_path = cases_dir / f"{in_path.stem}.out"
            emit(f"Writing expected answer for case {in_path.stem}.")
            solution_write(
                outputs["solution"], in_path, answer_path, limits.get("solutionTimeoutMs", 2000)
            )
            emit(f"Self-checking answer for case {in_path.stem}.")
            code, err = checker_compare(
                outputs["checker"],
                in_path,
                answer_path,
                answer_path,
                limits.get("solutionTimeoutMs", 2000),
            )
            if code != 0:
                raise JudgeError(f"checker self-check failed for {in_path.name}: {err}")

        if final_dir.exists():
            backup = final_dir.with_name(final_dir.name + f".old-{int(time.time() * 1000)}")
            final_dir.rename(backup)
        else:
            backup = None
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir.rename(final_dir)
        manifest = build_manifest(
            problem_id,
            profile,
            key,
            source_hashes(problem_id, root),
            case_summaries,
            final_dir,
            root,
        )
        write_json(final_dir / "manifest.json", manifest)
        if backup is not None:
            shutil.rmtree(backup)
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        raise
    finally:
        if lock_dir.exists():
            shutil.rmtree(lock_dir)
    emit(f"Generated data at {rel(final_dir, display_root)}.")
    print(f"Generated data: {rel(final_dir, display_root)}")
    return final_dir
