"""제출 도메인 로직과 파일시스템 변경 정책을 담당합니다.
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
    prepared_data_dirs: dict[str, Path] | None = None,
    prepared_tools: dict[str, Path] | None = None,
    language: str | None = None,
) -> Path:
    """제출 실행에 필요한 명령을 만들고 프로세스 종료 상태와 오류 출력을 해석합니다.

    Args:
        source (str | Path): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
        problem_id (str | None): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
        progress (Callable[[str], None] | None): 장시간 작업의 단계와 메시지를 UI 작업 상태로 전달하는 콜백입니다.
        stop_on_first_failure (bool): 제출 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        warmup_profile (str | None): 제출을 계산하거나 검증할 때 필요한 워밍업 프로필 입력입니다.

    Returns:
        Path: 검증된 제출 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """

    def emit(message: str) -> None:
        if progress is not None:
            progress(message)

    data_dirs: dict[str, Path] = {}
    if prepared_data_dirs:
        data_dirs.update(prepared_data_dirs)

    def profile_data_dir(target_profile: str) -> Path:
        prepared_data_dir = data_dirs.get(target_profile)
        if prepared_data_dir is not None:
            emit(f"Using prepared data at {rel(prepared_data_dir, display_root)}.")
            return prepared_data_dir
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
        language=language,
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
    tools = prepared_tools or compile_problem_tools(problem_id, root)
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
