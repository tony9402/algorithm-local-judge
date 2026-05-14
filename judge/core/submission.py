from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from judge.core.cases_compile import ensure_cases_compiled
from judge.core.compiler import compile_problem_tools, prepare_user_submission
from judge.core.errors import JudgeError
from judge.core.generation import cache_dir_for, generate
from judge.core.manifest import generation_key, validate_manifest
from judge.core.paths import cache_root, rel, repo_root, validate_safe_id
from judge.core.problem import load_problem
from judge.core.runner import checker_compare
from judge.utils.fs import read_json, write_json
from judge.utils.process import run_command_result


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
    problems_dir = (root / "problems").resolve()
    if problems_dir in source.parents:
        try:
            relative = source.relative_to(problems_dir)
            if relative.parts:
                inferred = relative.parts[0]
        except ValueError:
            inferred = None
    cwd = Path.cwd().resolve()
    if inferred is None and problems_dir in cwd.parents:
        relative = cwd.relative_to(problems_dir)
        if relative.parts:
            inferred = relative.parts[0]
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
    candidate = cache_dir_for(problem_id, key)
    if validate_manifest(candidate, problem_id, profile, key):
        return candidate
    return None


def run_submission(
    source: str | Path,
    problem_id: str | None = None,
    profile: str | None = None,
    root: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Compile, run, check, and record artifacts for one submission."""

    def emit(message: str) -> None:
        if progress is not None:
            progress(message)

    display_root = root or repo_root()
    source = Path(source)
    if not source.exists():
        raise JudgeError(f"source file not found: {source}")
    emit(f"Preparing submission file {source.name}.")
    problem_id = infer_problem_id(source, problem_id, root)
    _, _, metadata = load_problem(problem_id, root)
    profile = profile or metadata.get("defaultProfile", "full")
    validate_safe_id("profile", profile)
    emit(f"Compiling cases.yml for profile {profile}.")
    ensure_cases_compiled(problem_id, profile, root)
    run_id, run_dir = new_run_dir()
    emit(f"Created run {run_id}.")
    emit("Compiling or preparing user submission.")
    submission = prepare_user_submission(
        source.resolve(),
        run_dir,
        metadata.get("limits", {}).get("compileTimeoutMs", 5000),
        display_root,
    )
    emit(f"Submission language detected: {submission.language}.")
    cached_data_dir = latest_cache_for(problem_id, profile, root)
    if cached_data_dir is None:
        emit(f"No valid cached data for profile {profile}; generating test data.")
        data_dir = generate(problem_id, profile, root=root, progress=progress)
    else:
        data_dir = cached_data_dir
        emit(f"Using cached data at {rel(data_dir, display_root)}.")
    manifest = read_json(data_dir / "manifest.json")
    emit(f"Loaded {len(manifest['cases'])} test case(s).")
    emit("Preparing checker and problem tools.")
    tools = compile_problem_tools(problem_id, root)
    outputs_dir = run_dir / "outputs"
    wrong_dir = run_dir / "wrong"
    results: list[dict[str, Any]] = []
    status = "accepted"
    first_wrong = None
    max_time_ms = 0
    max_memory_bytes: int | None = None
    for index, case in enumerate(manifest["cases"], start=1):
        case_id = case["id"]
        emit(f"Running case {case_id} ({index}/{len(manifest['cases'])}).")
        in_path = data_dir / case["input"]
        answer_path = data_dir / case["answer"]
        actual_path = outputs_dir / f"{case_id}.actual"
        command_result = run_command_result(
            submission.command,
            metadata.get("limits", {}).get("userTimeoutMs", 2000),
            input_path=in_path,
            output_path=actual_path,
        )
        code = command_result.returncode
        stderr = command_result.stderr
        max_time_ms = max(max_time_ms, command_result.elapsed_ms)
        if command_result.memory_bytes is not None:
            max_memory_bytes = (
                command_result.memory_bytes
                if max_memory_bytes is None
                else max(max_memory_bytes, command_result.memory_bytes)
            )
        case_status = "ok"
        message = ""
        if code == 124:
            case_status = "time_limit"
            message = "time limit exceeded"
        elif code != 0:
            case_status = "runtime_error"
            message = stderr.decode("utf-8", errors="replace")
        else:
            checker_code, checker_message = checker_compare(
                tools["checker"],
                in_path,
                actual_path,
                answer_path,
                metadata.get("limits", {}).get("userTimeoutMs", 2000),
            )
            if checker_code != 0:
                case_status = "wrong_answer"
                message = checker_message
        emit(f"Case {case_id}: {case_status}.")
        results.append(
            {
                "case": case_id,
                "status": case_status,
                "message": message,
                "timeMs": command_result.elapsed_ms,
                "memoryBytes": command_result.memory_bytes,
            }
        )
        if case_status != "ok" and first_wrong is None:
            status = case_status
            first_wrong = case
            wrong_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(in_path, wrong_dir / f"{case_id}.in")
            shutil.copyfile(answer_path, wrong_dir / f"{case_id}.expected")
            if actual_path.exists():
                shutil.copyfile(actual_path, wrong_dir / f"{case_id}.actual")
            else:
                (wrong_dir / f"{case_id}.actual").write_text("", encoding="utf-8")
            break
    result = {
        "runId": run_id,
        "problemId": problem_id,
        "profile": profile,
        "language": submission.language,
        "status": status,
        "cases": results,
        "metrics": {
            "maxTimeMs": max_time_ms,
            "maxMemoryBytes": max_memory_bytes,
        },
    }
    write_json(run_dir / "result.json", result)
    if status == "accepted":
        emit(f"Accepted after {len(results)} case(s).")
        print(f"Accepted ({len(results)} case(s))")
        print(f"run: {rel(run_dir, display_root)}")
    else:
        case_id = first_wrong["id"]
        emit(f"{status.replace('_', ' ').title()} on case {case_id}.")
        print(f"{status.replace('_', ' ').title()} on case {case_id}")
        print(f"input:    {rel(wrong_dir / f'{case_id}.in', display_root)}")
        print(f"expected: {rel(wrong_dir / f'{case_id}.expected', display_root)}")
        print(f"actual:   {rel(wrong_dir / f'{case_id}.actual', display_root)}")
        print("")
        print("View:")
        print(f"  judge show {run_id} {case_id}")
    return run_dir
