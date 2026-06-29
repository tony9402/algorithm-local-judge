"""제출 워밍업 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from alj_core.submission_status import command_status
from alj_core.utils.fs import read_json
from alj_core.utils.process import CommandResult, run_command_result


def warm_up_submission(
    command: list[str],
    data_dir: Path,
    run_dir: Path,
    timeout_ms: int,
    profile: str,
    emit: Callable[[str], None],
    command_runner: Callable[..., CommandResult] = run_command_result,
) -> dict[str, Any] | None:
    """warm up 제출 실행에 필요한 명령을 만들고 프로세스 종료 상태와 오류 출력을 해석합니다.

    Args:
        command (list[str]): warm up 제출을 계산하거나 검증할 때 필요한 명령 입력입니다.
        data_dir (Path): 데이터 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        run_dir (Path): 실행 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        timeout_ms (int): 외부 프로세스가 끝나야 하는 제한 시간입니다. 단위는 밀리초입니다.
        profile (str): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        emit (Callable[[str], None]): warm up 제출을 계산하거나 검증할 때 필요한 emit 입력입니다.
        command_runner (Callable[..., CommandResult]): warm up 제출을 계산하거나 검증할 때 필요한 명령 실행기 입력입니다.

    Returns:
        dict[str, Any] | None: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 warm up 제출 데이터입니다.
    """
    manifest = read_json(data_dir / "manifest.json")
    cases = list(manifest.get("cases") or [])
    if not cases:
        emit(f"Skipping warmup for profile {profile}: no cases.")
        return None
    case = cases[0]
    case_id = case["id"]
    in_path = data_dir / case["input"]
    actual_path = run_dir / "warmup" / f"{profile}-{case_id}.actual"
    emit(f"Warming up submission with {profile} case {case_id}.")
    command_result = command_runner(
        command,
        timeout_ms,
        input_path=in_path,
        output_path=actual_path,
    )
    status, message = command_status(command_result)
    emit(f"Warmup case {case_id}: {status}.")
    return {
        "profile": profile,
        "case": case_id,
        "status": status,
        "message": message,
        "timeMs": command_result.elapsed_ms,
        "memoryBytes": command_result.memory_bytes,
    }
