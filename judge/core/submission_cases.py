"""제출 케이스 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge.core.runner import checker_compare
from judge.core.submission_result import copy_wrong_artifacts
from judge.core.submission_status import command_status, user_memory_limit_bytes
from judge.utils.process import CommandResult, run_command_result


@dataclass(frozen=True)
class SubmissionCasesResult:
    status: str
    results: list[dict[str, Any]]
    first_wrong: dict[str, Any] | None
    max_time_ms: int
    max_memory_bytes: int | None


def run_submission_cases(
    *,
    manifest: dict[str, Any],
    data_dir: Path,
    outputs_dir: Path,
    wrong_dir: Path,
    command: list[str],
    limits: dict[str, Any],
    checker_path: Path,
    emit: Callable[[str], None],
    stop_on_first_failure: bool,
    command_runner: Callable[..., CommandResult] = run_command_result,
    checker: Callable[[Path, Path, Path, Path, int], tuple[int, str]] = checker_compare,
) -> SubmissionCasesResult:
    """제출 케이스 실행에 필요한 명령을 만들고 프로세스 종료 상태와 오류 출력을 해석합니다.

        Args:
            manifest (dict[str, Any]): 문제팩 구성과 포함 파일을 설명하는 매니페스트 데이터입니다.
            data_dir (Path): 데이터 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
            outputs_dir (Path): outputs dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
            wrong_dir (Path): 오답 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
            command (list[str]): 제출 케이스을 계산하거나 검증할 때 필요한 명령 입력입니다.
            limits (dict[str, Any]): 제출 케이스을 계산하거나 검증할 때 필요한 limits 입력입니다.
            checker_path (Path): 체커 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
            emit (Callable[[str], None]): 제출 케이스을 계산하거나 검증할 때 필요한 emit 입력입니다.
            stop_on_first_failure (bool): 제출 케이스 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
            command_runner (Callable[..., CommandResult]): 제출 케이스을 계산하거나 검증할 때 필요한 명령 실행기 입력입니다.
            checker (Callable[[Path, Path, Path, Path, int], tuple[int, str]]): 입력, 제출 출력, 정답 출력을 비교하는 체커 실행 파일입니다.
    """
    results: list[dict[str, Any]] = []
    status = "accepted"
    first_wrong = None
    max_time_ms = 0
    max_memory_bytes: int | None = None
    timeout_ms = limits.get("userTimeoutMs", 2000)
    memory_limit = user_memory_limit_bytes(limits)
    cases = manifest["cases"]

    for index, case in enumerate(cases, start=1):
        case_id = case["id"]
        emit(f"Running case {case_id} ({index}/{len(cases)}).")
        in_path = data_dir / case["input"]
        answer_path = data_dir / case["answer"]
        actual_path = outputs_dir / f"{case_id}.actual"
        command_result = command_runner(
            command,
            timeout_ms,
            input_path=in_path,
            output_path=actual_path,
        )
        max_time_ms = max(max_time_ms, command_result.elapsed_ms)
        if command_result.memory_bytes is not None:
            max_memory_bytes = (
                command_result.memory_bytes
                if max_memory_bytes is None
                else max(max_memory_bytes, command_result.memory_bytes)
            )
        case_status, message = command_status(command_result)
        if memory_limit is not None and (
            command_result.memory_bytes is not None and command_result.memory_bytes > memory_limit
        ):
            case_status = "memory_limit"
            message = "memory limit exceeded"
        elif case_status == "ok":
            checker_code, checker_message = checker(
                checker_path,
                in_path,
                actual_path,
                answer_path,
                timeout_ms,
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
        if case_status != "ok":
            if first_wrong is None:
                status = case_status
                first_wrong = case
                copy_wrong_artifacts(wrong_dir, case_id, in_path, answer_path, actual_path)
            if stop_on_first_failure:
                break

    return SubmissionCasesResult(
        status=status,
        results=results,
        first_wrong=first_wrong,
        max_time_ms=max_time_ms,
        max_memory_bytes=max_memory_bytes,
    )


__all__ = [
    "SubmissionCasesResult",
    "run_submission_cases",
]
