"""submission 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from judge.core.cases_compile import ensure_cases_compiled
from judge.core.compiler import compile_problem_tools, prepare_user_submission
from judge.core.errors import JudgeError
from judge.core.generation import generate
from judge.core.paths import rel, repo_root, validate_safe_id
from judge.core.problem import load_problem
from judge.core.runner import checker_compare
from judge.core.submission_cases import run_submission_cases
from judge.core.submission_paths import infer_problem_id, latest_cache_for, new_run_dir
from judge.core.submission_result import build_submission_result, print_submission_result
from judge.core.submission_status import command_status, user_memory_limit_bytes
from judge.core.submission_warmup import warm_up_submission
from judge.utils.fs import read_json, write_json
from judge.utils.process import run_command_result


def run_submission(
    source: str | Path,
    problem_id: str | None = None,
    profile: str | None = None,
    root: Path | None = None,
    progress: Callable[[str], None] | None = None,
    stop_on_first_failure: bool = True,
    warmup_profile: str | None = None,
) -> Path:
    """run_submission 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (str | Path): `source` 값입니다.
        problem_id (str | None): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
        root (Path | None): `root` 값입니다.
        progress (Callable[[str], None] | None): `progress` 값입니다.
        stop_on_first_failure (bool): `stop_on_first_failure` 값입니다.
        warmup_profile (str | None): `warmup_profile` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
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

    data_dirs: dict[str, Path] = {}

    def profile_data_dir(target_profile: str) -> Path:
    """profile_data_dir 함수를 실행하고 결과를 반환합니다.
    
    Args:
        target_profile (str): `target_profile` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
        cached_data_dir = latest_cache_for(problem_id, target_profile, root)
        if cached_data_dir is None:
            emit(f"No valid cached data for profile {target_profile}; generating test data.")
            data_dir = generate(problem_id, target_profile, root=root, progress=progress)
        else:
            data_dir = cached_data_dir
            emit(f"Using cached data at {rel(data_dir, display_root)}.")
        data_dirs[target_profile] = data_dir
        return data_dir

    display_root = root or repo_root()
    source = Path(source)
    if not source.exists():
        raise JudgeError(f"source file not found: {source}")
    emit(f"Preparing submission file {source.name}.")
    problem_id = infer_problem_id(source, problem_id, root)
    _, _, metadata = load_problem(problem_id, root)
    profile = profile or metadata.get("defaultProfile", "full")
    limits = metadata.get("limits", {})
    validate_safe_id("profile", profile)
    emit(f"Compiling cases.yml for profile {profile}.")
    ensure_cases_compiled(problem_id, profile, root)
    run_id, run_dir = new_run_dir(root)
    emit(f"Created run {run_id}.")
    emit("Compiling or preparing user submission.")
    submission = prepare_user_submission(
        source.resolve(),
        run_dir,
        metadata.get("limits", {}).get("compileTimeoutMs", 5000),
        display_root,
    )
    emit(f"Submission language detected: {submission.language}.")
    warmup = None
    if warmup_profile:
        validate_safe_id("warmup profile", warmup_profile)
        warmup_data_dir = profile_data_dir(warmup_profile)
        warmup = warm_up_submission(
            submission.command,
            warmup_data_dir,
            run_dir,
            limits.get("userTimeoutMs", 2000),
            warmup_profile,
            emit,
            command_runner=run_command_result,
        )
    data_dir = data_dirs.get(profile) or profile_data_dir(profile)
    manifest = read_json(data_dir / "manifest.json")
    emit(f"Loaded {len(manifest['cases'])} test case(s).")
    emit("Preparing checker and problem tools.")
    tools = compile_problem_tools(problem_id, root)
    outputs_dir = run_dir / "outputs"
    wrong_dir = run_dir / "wrong"
    case_run = run_submission_cases(
        manifest=manifest,
        data_dir=data_dir,
        outputs_dir=outputs_dir,
        wrong_dir=wrong_dir,
        command=submission.command,
        limits=limits,
        checker_path=tools["checker"],
        emit=emit,
        stop_on_first_failure=stop_on_first_failure,
        command_runner=run_command_result,
        checker=checker_compare,
    )
    result = build_submission_result(
        run_id=run_id,
        problem_id=problem_id,
        profile=profile,
        language=submission.language,
        status=case_run.status,
        cases=case_run.results,
        max_time_ms=case_run.max_time_ms,
        max_memory_bytes=case_run.max_memory_bytes,
        warmup=warmup,
    )
    write_json(run_dir / "result.json", result)
    if case_run.status == "accepted":
        emit(f"Accepted after {len(case_run.results)} case(s).")
    else:
        case_id = case_run.first_wrong["id"]
        emit(f"{case_run.status.replace('_', ' ').title()} on case {case_id}.")
    print_submission_result(
        status=case_run.status,
        results=case_run.results,
        first_wrong=case_run.first_wrong,
        wrong_dir=wrong_dir,
        run_id=run_id,
        run_dir=run_dir,
        display_root=display_root,
    )
    return run_dir


__all__ = [
    "command_status",
    "infer_problem_id",
    "latest_cache_for",
    "new_run_dir",
    "run_submission",
    "user_memory_limit_bytes",
    "warm_up_submission",
]
