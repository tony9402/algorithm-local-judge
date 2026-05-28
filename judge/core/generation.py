"""생성 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
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
    return cache_root(root) / "problems" / problem_id / key


def acquire_generation_lock(
    problem_id: str,
    profile: str,
    key: str,
    root: Path | None = None,
    timeout_seconds: int = 30,
) -> Path:
    """acquire 생성 lock 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        key (str): 상태 맵, 로컬 스토리지, 객체에서 값을 찾는 키입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
        timeout_seconds (int): Git, 서버, 장시간 작업에 허용할 제한 시간입니다. 단위는 초입니다.

    Returns:
        Path: 검증된 acquire 생성 lock 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
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
    """generate 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        force (bool): 캐시나 기존 검사 결과를 무시하고 다시 실행할지 여부입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
        verbose (bool): 상세 경로, 설치 힌트, 원본 설정을 출력에 포함할지 여부입니다.
        progress (Callable[[str], None] | None): 장시간 작업의 단계와 메시지를 UI 작업 상태로 전달하는 콜백입니다.

    Returns:
        Path: 검증된 generate 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """

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
