"""stress 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import difflib
import random
import shutil
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from commons.generate import expand_cases, load_config, sha256_text
from judge.core.cases_compile import compile_problem_cases, format_compile_result
from judge.core.compiler import compile_problem_tools, prepare_user_submission
from judge.core.errors import JudgeError
from judge.core.paths import cache_root, ensure_inside, rel, validate_safe_id
from judge.core.problem import tool_paths
from judge.core.runner import checker_compare, solution_write, validator_check
from judge.core.solution_expectations import (
    discover_solution_expectations,
    ensure_reference_solution,
    filter_solution_expectations,
)
from judge.core.submission_cases import run_submission_cases
from judge.utils.fs import read_json, write_json
from judge.utils.process import run_command_result

MAX_STRESS_DURATION_SECONDS = 300
DEFAULT_STRESS_DURATION_SECONDS = 60
STRESS_PREVIEW_LIMIT = 12000
MIN_COMMAND_TIMEOUT_MS = 50


def _emit(
    progress: Callable[..., None] | None,
    message: str,
    *,
    current: int | None = None,
    total: int | None = None,
    label: str | None = None,
    **extra: Any,
) -> None:
"""_emit 함수를 실행하고 결과를 반환합니다.

Args:
    progress (Callable[..., None] | None): `progress` 값입니다.
    message (str): 메시지입니다.
    current (int | None): `current` 값입니다.
    total (int | None): `total` 값입니다.
    label (str | None): `label` 값입니다.
    **extra (Any): `extra` 값입니다.

Returns:
    None: 처리 결과를 반환합니다.
"""
    if progress is not None:
        progress(message, current=current, total=total, label=label, **extra)


def _check_cancel(cancel_token: Any | None) -> None:
"""_check_cancel 함수를 실행하고 결과를 반환합니다.

Args:
    cancel_token (Any | None): `cancel_token` 값입니다.

Returns:
    None: 처리 결과를 반환합니다.
"""
    if cancel_token is not None:
        cancel_token.check()


def _clamped_duration_seconds(value: int | None) -> int:
"""_clamped_duration_seconds 함수를 실행하고 결과를 반환합니다.

Args:
    value (int | None): 값입니다.

Returns:
    int: 처리 결과를 반환합니다.
"""
    if value is None:
        return DEFAULT_STRESS_DURATION_SECONDS
    try:
        duration = int(value)
    except (TypeError, ValueError):
        duration = DEFAULT_STRESS_DURATION_SECONDS
    return max(1, min(MAX_STRESS_DURATION_SECONDS, duration))


def _stress_root(workspace: Path) -> Path:
"""_stress_root 함수를 실행하고 결과를 반환합니다.

Args:
    workspace (Path): 작업 공간 객체입니다.

Returns:
    Path: 처리 결과를 반환합니다.
"""
    return cache_root(workspace) / "stress"


def _safe_run_id(run_id: str | None = None) -> str:
"""_safe_run_id 함수를 실행하고 결과를 반환합니다.

Args:
    run_id (str | None): `run_id` 값입니다.

Returns:
    str: 처리 결과를 반환합니다.
"""
    value = run_id or uuid.uuid4().hex
    validate_safe_id("stress run id", value)
    return value


def _stress_dir(workspace: Path, run_id: str) -> Path:
"""_stress_dir 함수를 실행하고 결과를 반환합니다.

Args:
    workspace (Path): 작업 공간 객체입니다.
    run_id (str): `run_id` 값입니다.

Returns:
    Path: 처리 결과를 반환합니다.
"""
    return ensure_inside(_stress_root(workspace) / run_id, _stress_root(workspace))


def _profile_cases(config: Mapping[str, Any], profile: str) -> list[Any]:
"""_profile_cases 함수를 실행하고 결과를 반환합니다.

Args:
    config (Mapping[str, Any]): 동작 설정입니다.
    profile (str): `profile` 값입니다.

Returns:
    list[Any]: 처리 결과를 반환합니다.
"""
    profiles = config.get("profiles", {})
    if not isinstance(profiles, Mapping):
        raise JudgeError("cases.yml profiles must be a mapping")
    if profile == "full" and profile not in profiles:
        cases_source: list[Any] = []
        for profile_config in profiles.values():
            if isinstance(profile_config, Mapping):
                cases_source.extend(profile_config.get("cases", []) or [])
        return cases_source
    if profile not in profiles:
        raise JudgeError(f"unknown profile: {profile}")
    profile_config = profiles[profile]
    if not isinstance(profile_config, Mapping):
        raise JudgeError(f"profile must be a mapping: {profile}")
    cases_source = profile_config.get("cases", [])
    if not isinstance(cases_source, list):
        raise JudgeError(f"profile cases must be a list: {profile}")
    return cases_source


def _generator_cases(config_path: Path, profile: str) -> list[dict[str, Any]]:
"""_generator_cases 함수를 실행하고 결과를 반환합니다.

Args:
    config_path (Path): `config_path` 값입니다.
    profile (str): `profile` 값입니다.

Returns:
    list[dict[str, Any]]: 처리 결과를 반환합니다.
"""
    config = load_config(config_path)
    try:
        cases = expand_cases(_profile_cases(config, profile))
    except Exception as exc:
        raise JudgeError(f"cases.yml expansion failed: {exc}") from exc
    generator_cases = [case for case in cases if case.get("type") == "generator"]
    if not generator_cases:
        raise JudgeError(f"profile {profile} has no generator cases to stress")
    return generator_cases


def _solution_key(path: Path, problem_dir: Path) -> str:
"""_solution_key 함수를 실행하고 결과를 반환합니다.

Args:
    path (Path): 경로 문자열입니다.
    problem_dir (Path): `problem_dir` 값입니다.

Returns:
    str: 처리 결과를 반환합니다.
"""
    relative = rel(path, problem_dir).replace("\\", "/")
    digest = sha256_text(relative)[:10]
    stem = (
        relative.replace("/", "__")
        .replace(".", "_")
        .replace(" ", "_")
        .replace("-", "_")
    )
    return f"{stem[:54]}-{digest}"


def _remaining_ms(deadline: float, configured_ms: int | None) -> int:
"""_remaining_ms 함수를 실행하고 결과를 반환합니다.

Args:
    deadline (float): `deadline` 값입니다.
    configured_ms (int | None): `configured_ms` 값입니다.

Returns:
    int: 처리 결과를 반환합니다.
"""
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining < MIN_COMMAND_TIMEOUT_MS:
        raise JudgeError("stress duration elapsed while a case was running")
    if configured_ms is None:
        return remaining
    return max(MIN_COMMAND_TIMEOUT_MS, min(int(configured_ms), remaining))


def _generator_command(generator: Path, case: Mapping[str, Any]) -> list[str]:
"""_generator_command 함수를 실행하고 결과를 반환합니다.

Args:
    generator (Path): `generator` 값입니다.
    case (Mapping[str, Any]): `case` 값입니다.

Returns:
    list[str]: 처리 결과를 반환합니다.
"""
    seed = case.get("seed")
    if seed is None:
        raise JudgeError(f"generator case requires seed: {case.get('name')}")
    command = [str(generator), str(seed)]
    args = case.get("args", {}) or {}
    if not isinstance(args, Mapping):
        raise JudgeError(f"generator args must be a mapping: {case.get('name')}")
    for key, value in args.items():
        command.append(f"--{key}={value}")
    return command


def _run_generator(
    generator: Path,
    case: Mapping[str, Any],
    timeout_ms: int,
) -> str:
"""_run_generator 함수를 실행하고 결과를 반환합니다.

Args:
    generator (Path): `generator` 값입니다.
    case (Mapping[str, Any]): `case` 값입니다.
    timeout_ms (int): `timeout_ms` 값입니다.

Returns:
    str: 처리 결과를 반환합니다.
"""
    result = run_command_result(_generator_command(generator, case), timeout_ms)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        detail = (
            f"generator failed for case {case.get('name')} "
            f"(exit code {result.returncode})"
        )
        if stderr:
            detail = f"{detail}: {stderr}"
        raise JudgeError(detail)
    return result.stdout.decode("utf-8", errors="replace")


def _status_from_submission_result(result: Any) -> str:
"""_status_from_submission_result 함수를 실행하고 결과를 반환합니다.

Args:
    result (Any): `result` 값입니다.

Returns:
    str: 처리 결과를 반환합니다.
"""
    return "accepted" if result.status == "accepted" else result.status


def _stress_status_matches(expected_status: str, actual_status: str) -> bool:
"""_stress_status_matches 함수를 실행하고 결과를 반환합니다.

Args:
    expected_status (str): `expected_status` 값입니다.
    actual_status (str): `actual_status` 값입니다.

Returns:
    bool: 처리 결과를 반환합니다.
"""
    if actual_status == expected_status:
        return True
    return expected_status != "accepted" and actual_status == "accepted"


def _case_manifest(problem_id: str, profile: str, case_id: str, case_name: str) -> dict[str, Any]:
"""_case_manifest 함수를 실행하고 결과를 반환합니다.

Args:
    problem_id (str): 문제 ID입니다.
    profile (str): `profile` 값입니다.
    case_id (str): `case_id` 값입니다.
    case_name (str): `case_name` 값입니다.

Returns:
    dict[str, Any]: 처리 결과를 반환합니다.
"""
    return {
        "problemId": problem_id,
        "profile": f"stress:{profile}",
        "cases": [
            {
                "id": case_id,
                "name": case_name,
                "input": f"cases/{case_id}.in",
                "answer": f"cases/{case_id}.out",
            }
        ],
    }


def _diff_text(expected: Path, actual: Path) -> str:
"""_diff_text 함수를 실행하고 결과를 반환합니다.

Args:
    expected (Path): `expected` 값입니다.
    actual (Path): `actual` 값입니다.

Returns:
    str: 처리 결과를 반환합니다.
"""
    expected_lines = expected.read_text(encoding="utf-8", errors="replace").splitlines(True)
    actual_lines = actual.read_text(encoding="utf-8", errors="replace").splitlines(True)
    return "".join(
        difflib.unified_diff(
            expected_lines,
            actual_lines,
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )


def _copy_mismatch_artifacts(
    *,
    run_dir: Path,
    case_id: str,
    solution_key: str,
    input_path: Path,
    expected_path: Path,
    actual_path: Path | None,
    metadata: dict[str, Any],
) -> dict[str, str]:
"""_copy_mismatch_artifacts 함수를 실행하고 결과를 반환합니다.

Args:
    run_dir (Path): `run_dir` 값입니다.
    case_id (str): `case_id` 값입니다.
    solution_key (str): `solution_key` 값입니다.
    input_path (Path): `input_path` 값입니다.
    expected_path (Path): `expected_path` 값입니다.
    actual_path (Path | None): `actual_path` 값입니다.
    metadata (dict[str, Any]): `metadata` 값입니다.

Returns:
    dict[str, str]: 처리 결과를 반환합니다.
"""
    artifact_dir = run_dir / "mismatches" / case_id / solution_key
    artifact_dir.mkdir(parents=True, exist_ok=True)
    input_copy = artifact_dir / "input.txt"
    expected_copy = artifact_dir / "expected.txt"
    actual_copy = artifact_dir / "actual.txt"
    diff_path = artifact_dir / "diff.txt"
    shutil.copyfile(input_path, input_copy)
    shutil.copyfile(expected_path, expected_copy)
    if actual_path is not None and actual_path.exists():
        shutil.copyfile(actual_path, actual_copy)
    else:
        actual_copy.write_text(metadata.get("message", "") + "\n", encoding="utf-8")
    diff_path.write_text(_diff_text(expected_copy, actual_copy), encoding="utf-8")
    write_json(artifact_dir / "metadata.json", metadata)
    return {
        "input": rel(input_copy, run_dir),
        "expected": rel(expected_copy, run_dir),
        "actual": rel(actual_copy, run_dir),
        "diff": rel(diff_path, run_dir),
        "metadata": rel(artifact_dir / "metadata.json", run_dir),
    }


def _remove_case_artifacts(run_dir: Path, case_id: str, solution_keys: list[str]) -> None:
"""_remove_case_artifacts 함수를 실행하고 결과를 반환합니다.

Args:
    run_dir (Path): `run_dir` 값입니다.
    case_id (str): `case_id` 값입니다.
    solution_keys (list[str]): `solution_keys` 값입니다.

Returns:
    None: 처리 결과를 반환합니다.
"""
    for relative in [f"cases/{case_id}.in", f"cases/{case_id}.out"]:
        path = run_dir / relative
        if path.exists():
            path.unlink()
    for key in solution_keys:
        outputs_dir = run_dir / "outputs" / key
        actual = outputs_dir / f"{case_id}.actual"
        if actual.exists():
            actual.unlink()
        try:
            outputs_dir.rmdir()
        except OSError:
            pass


def _progress_payload(
    *,
    start: float,
    deadline: float,
    duration_seconds: int,
    iterations: int,
    mismatch_count: int,
    seed: int | None = None,
    max_cases: int | None = None,
) -> dict[str, Any]:
"""_progress_payload 함수를 실행하고 결과를 반환합니다.

Args:
    start (float): `start` 값입니다.
    deadline (float): `deadline` 값입니다.
    duration_seconds (int): `duration_seconds` 값입니다.
    iterations (int): `iterations` 값입니다.
    mismatch_count (int): `mismatch_count` 값입니다.
    seed (int | None): `seed` 값입니다.
    max_cases (int | None): `max_cases` 값입니다.

Returns:
    dict[str, Any]: 처리 결과를 반환합니다.
"""
    elapsed = max(0.0, time.monotonic() - start)
    remaining = max(0.0, deadline - time.monotonic())
    if max_cases:
        current = min(iterations, max_cases)
        total = max_cases
    else:
        current = min(duration_seconds, int(round(elapsed)))
        total = duration_seconds
    percent = int(round((current / total) * 100)) if total else 0
    return {
        "current": current,
        "total": total,
        "iteration": iterations,
        "mismatches": mismatch_count,
        "seed": seed,
        "elapsedSeconds": round(elapsed, 1),
        "remainingSeconds": round(remaining, 1),
        "percent": max(0, min(100, percent)),
    }


def stress_test_solutions(
    workspace: Path,
    problem_id: str,
    profile: str = "hidden",
    *,
    duration_seconds: int = DEFAULT_STRESS_DURATION_SECONDS,
    max_cases: int | None = None,
    solutions: list[str] | None = None,
    stop_on_first_mismatch: bool = True,
    cancel_token: Any | None = None,
    progress: Callable[..., None] | None = None,
    rng: random.Random | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """stress_test_solutions 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        profile (str): `profile` 값입니다.
        duration_seconds (int): `duration_seconds` 값입니다.
        max_cases (int | None): `max_cases` 값입니다.
        solutions (list[str] | None): `solutions` 값입니다.
        stop_on_first_mismatch (bool): `stop_on_first_mismatch` 값입니다.
        cancel_token (Any | None): `cancel_token` 값입니다.
        progress (Callable[..., None] | None): `progress` 값입니다.
        rng (random.Random | None): `rng` 값입니다.
        run_id (str | None): `run_id` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    validate_safe_id("problem id", problem_id)
    validate_safe_id("profile", profile)
    duration_seconds = _clamped_duration_seconds(duration_seconds)
    run_id = _safe_run_id(run_id)
    run_dir = _stress_dir(workspace, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    deadline = start + duration_seconds
    random_source = rng or random.SystemRandom()
    seen_seeds: set[int] = set()
    iterations = 0
    mismatches: list[dict[str, Any]] = []
    solution_keys: list[str] = []

    _emit(
        progress,
        f"Stress 테스트 시작: {problem_id} · {profile}.",
        current=0,
        total=max_cases or duration_seconds,
        label="stress",
        iteration=0,
        mismatches=0,
        elapsedSeconds=0,
        remainingSeconds=duration_seconds,
        percent=0,
    )
    _check_cancel(cancel_token)
    problem_dir, _, metadata, paths = tool_paths(problem_id, workspace)
    limits = dict(metadata.get("limits") or {})
    ensure_reference_solution(problem_id, workspace)

    cases_result = compile_problem_cases(problem_id, profile, workspace)
    if not cases_result.valid:
        raise JudgeError("cases.yml compile failed\n\n" + format_compile_result(cases_result))
    template_cases = _generator_cases(paths["generatorConfig"], profile)

    _emit(progress, "Stress 테스트용 도구를 컴파일합니다.", label="stress")
    outputs = compile_problem_tools(problem_id, workspace, progress=lambda message: _emit(progress, message, label="stress"))
    _check_cancel(cancel_token)

    all_expectations = discover_solution_expectations(problem_dir)
    expectations = filter_solution_expectations(all_expectations, problem_dir, solutions)
    if not expectations:
        raise JudgeError("no solution files selected for stress test")

    prepared = []
    for index, expectation in enumerate(expectations, start=1):
        _check_cancel(cancel_token)
        key = _solution_key(expectation.path, problem_dir)
        solution_keys.append(key)
        run_subdir = run_dir / "submissions" / key
        compile_status = None
        compile_message = ""
        command: list[str] | None = None
        try:
            timeout_ms = _remaining_ms(deadline, limits.get("compileTimeoutMs", 5000))
            command = prepare_user_submission(
                expectation.path,
                run_subdir,
                timeout_ms,
                workspace,
            ).command
        except JudgeError as exc:
            compile_status = "compile_error"
            compile_message = str(exc)
        prepared.append(
            {
                "expectation": expectation,
                "key": key,
                "source": rel(expectation.path, problem_dir),
                "command": command,
                "compileStatus": compile_status,
                "compileMessage": compile_message,
            }
        )
        _emit(
            progress,
            f"Stress 대상 솔루션 준비 {index}/{len(expectations)}.",
            label="stress",
            preparedSolutions=index,
            totalSolutions=len(expectations),
        )

    while time.monotonic() < deadline and (max_cases is None or iterations < max_cases):
        _check_cancel(cancel_token)
        iterations += 1
        seed = random_source.randrange(1, 2**63 - 1)
        while seed in seen_seeds:
            seed = random_source.randrange(1, 2**63 - 1)
        seen_seeds.add(seed)
        template = random_source.choice(template_cases)
        case = dict(template)
        case["seed"] = seed
        case_id = f"{iterations:06d}"
        generator_case_name = str(template.get("name") or case_id)
        case_name = f"stress-{case_id}"
        input_path = run_dir / "cases" / f"{case_id}.in"
        expected_path = run_dir / "cases" / f"{case_id}.out"
        input_path.parent.mkdir(parents=True, exist_ok=True)
        _emit(
            progress,
            f"Stress 반복 {iterations}: seed {seed}.",
            label="stress",
            **_progress_payload(
                start=start,
                deadline=deadline,
                duration_seconds=duration_seconds,
                iterations=iterations,
                mismatch_count=len(mismatches),
                seed=seed,
                max_cases=max_cases,
            ),
        )
        generated = _run_generator(
            outputs["generator"],
            case,
            _remaining_ms(deadline, limits.get("generationTimeoutMs", 5000)),
        )
        input_path.write_text(generated, encoding="utf-8")
        _check_cancel(cancel_token)
        validator_check(
            outputs["validator"],
            input_path,
            _remaining_ms(deadline, limits.get("generationTimeoutMs", 5000)),
            profile=profile,
            case_index=iterations,
            case_total=max_cases,
            root=workspace,
        )
        _check_cancel(cancel_token)
        solution_write(
            outputs["solution"],
            input_path,
            expected_path,
            _remaining_ms(deadline, limits.get("solutionTimeoutMs", 2000)),
        )
        checker_code, checker_message = checker_compare(
            outputs["checker"],
            input_path,
            expected_path,
            expected_path,
            _remaining_ms(deadline, limits.get("solutionTimeoutMs", 2000)),
        )
        if checker_code != 0:
            raise JudgeError(f"checker self-check failed for stress case {case_id}: {checker_message}")

        case_mismatched = False
        manifest = _case_manifest(problem_id, profile, case_id, case_name)
        for prepared_solution in prepared:
            _check_cancel(cancel_token)
            expectation = prepared_solution["expectation"]
            solution_key = prepared_solution["key"]
            outputs_dir = run_dir / "outputs" / solution_key
            wrong_dir = run_dir / "wrong" / solution_key
            actual_path = outputs_dir / f"{case_id}.actual"
            if prepared_solution["compileStatus"] == "compile_error":
                actual_status = "compile_error"
                message = prepared_solution["compileMessage"]
                case_results = [
                    {
                        "case": case_id,
                        "status": actual_status,
                        "message": message,
                        "timeMs": None,
                        "memoryBytes": None,
                    }
                ]
                metrics = {"maxTimeMs": None, "maxMemoryBytes": None}
            else:
                iteration_limits = {
                    **limits,
                    "userTimeoutMs": _remaining_ms(deadline, limits.get("userTimeoutMs", 2000)),
                }
                result = run_submission_cases(
                    manifest=manifest,
                    data_dir=run_dir,
                    outputs_dir=outputs_dir,
                    wrong_dir=wrong_dir,
                    command=prepared_solution["command"],
                    limits=iteration_limits,
                    checker_path=outputs["checker"],
                    emit=lambda message: _emit(progress, message, label="stress"),
                    stop_on_first_failure=True,
                )
                actual_status = _status_from_submission_result(result)
                first_case = result.results[0] if result.results else {}
                message = str(first_case.get("message") or "")
                case_results = result.results
                metrics = {
                    "maxTimeMs": result.max_time_ms,
                    "maxMemoryBytes": result.max_memory_bytes,
                }
            if _stress_status_matches(expectation.status, actual_status):
                continue
            case_mismatched = True
            mismatch = {
                "caseId": case_id,
                "caseName": case_name,
                "solutionKey": solution_key,
                "solution": prepared_solution["source"],
                "expectedStatus": expectation.status,
                "actualStatus": actual_status,
                "message": message,
                "seed": seed,
                "args": dict(case.get("args") or {}),
                "generatorCaseName": generator_case_name,
                "inputHash": sha256_text(generated),
                "cases": case_results,
                "metrics": metrics,
            }
            mismatch["artifacts"] = _copy_mismatch_artifacts(
                run_dir=run_dir,
                case_id=case_id,
                solution_key=solution_key,
                input_path=input_path,
                expected_path=expected_path,
                actual_path=actual_path,
                metadata=mismatch,
            )
            mismatches.append(mismatch)
            _emit(
                progress,
                (
                    f"Mismatch 발견 {case_id}: "
                    f"{prepared_solution['source']} expected {expectation.status}, got {actual_status}."
                ),
                label="stress",
                **_progress_payload(
                    start=start,
                    deadline=deadline,
                    duration_seconds=duration_seconds,
                    iterations=iterations,
                    mismatch_count=len(mismatches),
                    seed=seed,
                    max_cases=max_cases,
                ),
            )
            if stop_on_first_mismatch:
                break
        if not case_mismatched:
            _remove_case_artifacts(run_dir, case_id, solution_keys)
        if mismatches and stop_on_first_mismatch:
            break

    elapsed = round(time.monotonic() - start, 3)
    result_payload = {
        "problemId": problem_id,
        "profile": profile,
        "stressRunId": run_id,
        "passed": not mismatches,
        "iterations": iterations,
        "durationSeconds": duration_seconds,
        "requestedMaxCases": max_cases,
        "elapsedSeconds": elapsed,
        "mismatchCount": len(mismatches),
        "mismatches": mismatches,
        "checkedSolutions": [
            {
                "solution": item["source"],
                "solutionKey": item["key"],
                "expectedStatus": item["expectation"].status,
            }
            for item in prepared
        ],
    }
    write_json(run_dir / "result.json", result_payload)
    _emit(
        progress,
        "Stress 테스트 완료." if not mismatches else "Stress 테스트가 mismatch에서 중단되었습니다.",
        label="stress",
        **_progress_payload(
            start=start,
            deadline=deadline,
            duration_seconds=duration_seconds,
            iterations=iterations,
            mismatch_count=len(mismatches),
            max_cases=max_cases,
        ),
    )
    return result_payload


def _read_stress_result(workspace: Path, run_id: str) -> dict[str, Any]:
"""_read_stress_result 함수를 실행하고 결과를 반환합니다.

Args:
    workspace (Path): 작업 공간 객체입니다.
    run_id (str): `run_id` 값입니다.

Returns:
    dict[str, Any]: 처리 결과를 반환합니다.
"""
    run_id = _safe_run_id(run_id)
    result_path = _stress_dir(workspace, run_id) / "result.json"
    if not result_path.exists():
        raise JudgeError(f"stress run not found: {run_id}")
    return read_json(result_path)


def stress_mismatch_metadata(
    workspace: Path,
    run_id: str,
    case_id: str,
    solution_key: str,
) -> dict[str, Any]:
"""stress_mismatch_metadata 함수를 실행하고 결과를 반환합니다.

Args:
    workspace (Path): 작업 공간 객체입니다.
    run_id (str): `run_id` 값입니다.
    case_id (str): `case_id` 값입니다.
    solution_key (str): `solution_key` 값입니다.

Returns:
    dict[str, Any]: 처리 결과를 반환합니다.
"""
    validate_safe_id("case id", case_id)
    validate_safe_id("solution key", solution_key)
    result = _read_stress_result(workspace, run_id)
    for mismatch in result.get("mismatches", []):
        if mismatch.get("caseId") == case_id and mismatch.get("solutionKey") == solution_key:
            return mismatch
    raise JudgeError(f"stress mismatch not found: {case_id}/{solution_key}")


def _preview_text(path: Path, limit: int = STRESS_PREVIEW_LIMIT) -> dict[str, Any]:
"""_preview_text 함수를 실행하고 결과를 반환합니다.

Args:
    path (Path): 경로 문자열입니다.
    limit (int): `limit` 값입니다.

Returns:
    dict[str, Any]: 처리 결과를 반환합니다.
"""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= limit:
        return {"text": text, "truncated": False, "omittedChars": 0}
    omitted = len(text) - limit
    return {
        "text": text[:limit].rstrip() + f"\n\n... truncated after {limit} chars, omitted {omitted} chars ...",
        "truncated": True,
        "omittedChars": omitted,
    }


def stress_mismatch_preview(
    workspace: Path,
    run_id: str,
    case_id: str,
    solution_key: str,
    *,
    limit: int = STRESS_PREVIEW_LIMIT,
) -> dict[str, Any]:
"""stress_mismatch_preview 함수를 실행하고 결과를 반환합니다.

Args:
    workspace (Path): 작업 공간 객체입니다.
    run_id (str): `run_id` 값입니다.
    case_id (str): `case_id` 값입니다.
    solution_key (str): `solution_key` 값입니다.
    limit (int): `limit` 값입니다.

Returns:
    dict[str, Any]: 처리 결과를 반환합니다.
"""
    metadata = stress_mismatch_metadata(workspace, run_id, case_id, solution_key)
    run_dir = _stress_dir(workspace, run_id)
    artifact_dir = run_dir / "mismatches" / case_id / solution_key
    paths = {
        "input": artifact_dir / "input.txt",
        "expected": artifact_dir / "expected.txt",
        "actual": artifact_dir / "actual.txt",
        "diff": artifact_dir / "diff.txt",
    }
    result = {
        "stressRunId": run_id,
        "caseId": case_id,
        "solutionKey": solution_key,
        "previewLimit": limit,
        "metadata": metadata,
        "truncation": {},
    }
    for key, path in paths.items():
        preview = _preview_text(path, limit)
        result[key] = preview["text"]
        result["truncation"][key] = {
            "truncated": preview["truncated"],
            "omittedChars": preview["omittedChars"],
        }
    return result


def _yaml_scalar(value: Any) -> str:
"""_yaml_scalar 함수를 실행하고 결과를 반환합니다.

Args:
    value (Any): 값입니다.

Returns:
    str: 처리 결과를 반환합니다.
"""
    dumped = yaml.safe_dump(
        value,
        allow_unicode=True,
        default_flow_style=True,
        sort_keys=False,
    ).strip()
    if dumped.endswith("\n..."):
        dumped = dumped[:-4].strip()
    return dumped


def _case_block(case_name: str, mode: str, metadata: Mapping[str, Any], input_text: str) -> str:
"""_case_block 함수를 실행하고 결과를 반환합니다.

Args:
    case_name (str): `case_name` 값입니다.
    mode (str): `mode` 값입니다.
    metadata (Mapping[str, Any]): `metadata` 값입니다.
    input_text (str): `input_text` 값입니다.

Returns:
    str: 처리 결과를 반환합니다.
"""
    if mode == "fixed":
        content = input_text if input_text.endswith("\n") else input_text + "\n"
        lines = [
            f"      - name: {_yaml_scalar(case_name)}",
            "        type: fixed",
            "        content: |",
        ]
        lines.extend(f"          {line}" if line else "          " for line in content.splitlines())
        return "\n".join(lines) + "\n"
    if mode == "generator":
        lines = [
            f"      - name: {_yaml_scalar(case_name)}",
            "        type: generator",
            f"        seed: {_yaml_scalar(metadata.get('seed'))}",
        ]
        args = metadata.get("args") or {}
        if args:
            lines.append("        args:")
            for key, value in args.items():
                lines.append(f"          {key}: {_yaml_scalar(value)}")
        return "\n".join(lines) + "\n"
    raise JudgeError(f"unsupported stress append mode: {mode}")


def _profile_case_names(workspace: Path, problem_id: str, profile: str) -> set[str]:
"""_profile_case_names 함수를 실행하고 결과를 반환합니다.

Args:
    workspace (Path): 작업 공간 객체입니다.
    problem_id (str): 문제 ID입니다.
    profile (str): `profile` 값입니다.

Returns:
    set[str]: 처리 결과를 반환합니다.
"""
    compiled = compile_problem_cases(problem_id, profile, workspace)
    if not compiled.valid:
        raise JudgeError("cases.yml compile failed\n\n" + format_compile_result(compiled))
    names: set[str] = set()
    for compiled_profile in compiled.profiles:
        if compiled_profile.name == profile:
            names.update(case.name for case in compiled_profile.cases)
    return names


def _existing_input_hashes(workspace: Path, problem_id: str, profile: str) -> set[str]:
"""_existing_input_hashes 함수를 실행하고 결과를 반환합니다.

Args:
    workspace (Path): 작업 공간 객체입니다.
    problem_id (str): 문제 ID입니다.
    profile (str): `profile` 값입니다.

Returns:
    set[str]: 처리 결과를 반환합니다.
"""
    _, _, metadata, paths = tool_paths(problem_id, workspace)
    config = load_config(paths["generatorConfig"])
    outputs = compile_problem_tools(problem_id, workspace)
    hashes: set[str] = set()
    for case in expand_cases(_profile_cases(config, profile)):
        case_type = case.get("type")
        if case_type == "fixed":
            content = case.get("content", "")
        elif case_type == "generator":
            content = _run_generator(
                outputs["generator"],
                case,
                int((metadata.get("limits") or {}).get("generationTimeoutMs", 5000)),
            )
        else:
            continue
        hashes.add(sha256_text(content))
    return hashes


def _insert_case_block(text: str, profile: str, block: str) -> str:
"""_insert_case_block 함수를 실행하고 결과를 반환합니다.

Args:
    text (str): `text` 값입니다.
    profile (str): `profile` 값입니다.
    block (str): `block` 값입니다.

Returns:
    str: 처리 결과를 반환합니다.
"""
    lines = text.splitlines()
    profile_line = None
    for index, line in enumerate(lines):
        if line == f"  {profile}:":
            profile_line = index
            break
    if profile_line is None:
        raise JudgeError(f"profile does not exist in cases.yml: {profile}")
    cases_line = None
    end_line = len(lines)
    for index in range(profile_line + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            end_line = index
            break
        if line == "    cases:":
            cases_line = index
    if cases_line is None or cases_line >= end_line:
        raise JudgeError(f"profile has no cases list: {profile}")
    insert_at = end_line
    block_lines = block.rstrip("\n").splitlines()
    next_lines = [*lines[:insert_at], *block_lines, *lines[insert_at:]]
    return "\n".join(next_lines) + "\n"


def append_stress_case(
    workspace: Path,
    problem_id: str,
    profile: str,
    run_id: str,
    case_id: str,
    solution_key: str,
    *,
    mode: str,
    name: str | None = None,
) -> dict[str, Any]:
    """append_stress_case 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        profile (str): `profile` 값입니다.
        run_id (str): `run_id` 값입니다.
        case_id (str): `case_id` 값입니다.
        solution_key (str): `solution_key` 값입니다.
        mode (str): `mode` 값입니다.
        name (str | None): 이름입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    validate_safe_id("problem id", problem_id)
    validate_safe_id("profile", profile)
    if profile == "full":
        raise JudgeError("full is a synthetic profile; append to sample or hidden instead")
    metadata = stress_mismatch_metadata(workspace, run_id, case_id, solution_key)
    preview = stress_mismatch_preview(workspace, run_id, case_id, solution_key)
    case_name = (name or f"{metadata['caseName']}-{mode}").strip()
    if not case_name:
        raise JudgeError("case name is required")
    problem_dir, _, _, paths = tool_paths(problem_id, workspace)
    cases_path = ensure_inside(paths["generatorConfig"], problem_dir)
    before = cases_path.read_text(encoding="utf-8")
    names = _profile_case_names(workspace, problem_id, profile)
    if case_name in names:
        raise JudgeError(f"case name already exists: {case_name}")
    existing_hashes = _existing_input_hashes(workspace, problem_id, profile)
    if metadata.get("inputHash") in existing_hashes:
        raise JudgeError("duplicate input hash already exists in this profile")
    block = _case_block(case_name, mode, metadata, preview["input"])
    after = _insert_case_block(before, profile, block)
    cases_path.write_text(after, encoding="utf-8")
    try:
        compiled = compile_problem_cases(problem_id, profile, workspace)
        if not compiled.valid:
            raise JudgeError("cases.yml compile failed\n\n" + format_compile_result(compiled))
    except Exception:
        cases_path.write_text(before, encoding="utf-8")
        raise
    return {
        "problemId": problem_id,
        "profile": profile,
        "caseName": case_name,
        "mode": mode,
        "path": rel(cases_path, workspace),
        "compile": compiled.to_dict(),
        "inputHash": metadata.get("inputHash"),
    }


__all__ = [
    "MAX_STRESS_DURATION_SECONDS",
    "append_stress_case",
    "stress_mismatch_metadata",
    "stress_mismatch_preview",
    "stress_test_solutions",
]
