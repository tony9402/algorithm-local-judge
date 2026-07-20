"""packflow 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from alj_core.pack import build_pack, build_pack_for_problem_ids
from alj_core.paths import current_platform_id, rel
from alj_core.solution_validation import (
    discover_solution_expectations,
    verify_problem_solutions,
)
from problem_studio.core.workspace import problem_dir

SOLUTION_WARMUP_PROFILE = "sample"


def list_solutions(workspace: Path, problem_id: str) -> list[dict[str, Any]]:
    """현재 설정과 파일시스템을 기준으로 솔루션 목록을 조회합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.

    Returns:
        list[dict[str, Any]]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 데이터입니다.
    """
    base = problem_dir(workspace, problem_id)
    return [
        {
            "path": rel(expectation.path, base),
            "token": expectation.token,
            "expectedStatus": expectation.status,
        }
        for expectation in discover_solution_expectations(base)
    ]


def verify_solutions(
    workspace: Path,
    problem_id: str,
    profile: str = "hidden",
    progress: Callable[[str], None] | None = None,
    raise_on_failure: bool = True,
    solutions: list[str] | None = None,
    on_check: Callable[[Any, int, int], None] | None = None,
    max_workers: int | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    return verify_problem_solutions(
        problem_id,
        profile,
        workspace,
        progress=progress,
        raise_on_failure=raise_on_failure,
        solution_paths=solutions,
        warmup_profile=SOLUTION_WARMUP_PROFILE,
        on_check=on_check,
        max_workers=max_workers,
        cancel_check=cancel_check,
    ).to_dict(workspace)


def build_problem_pack(
    workspace: Path,
    problem_id: str,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    cancel_token: Any | None = None,
) -> dict[str, Any]:
    """문제 팩에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        pack_id (str): 설치, 삭제, 조회할 문제 팩을 구분하는 ID입니다.
        output_dir (Path): 출력 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        platform_id (str | None): platform ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.
        verify_profile (str): 문제 팩을 계산하거나 검증할 때 필요한 verify 프로필 입력입니다.
        cancel_token (Any | None): 사용자가 취소한 작업인지 확인하기 위한 토큰입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 팩 데이터입니다.
    """
    if cancel_token:
        cancel_token.check()
    resolved_output_dir = output_dir if output_dir.is_absolute() else workspace / output_dir
    result = build_pack(
        problem_dir(workspace, problem_id),
        pack_id,
        platform_id or current_platform_id(),
        resolved_output_dir,
        verify_profile,
        warmup_profile=SOLUTION_WARMUP_PROFILE,
    )
    if cancel_token:
        cancel_token.check()
    return {
        "archivePath": str(result.archive_path),
        "archiveLabel": rel(result.archive_path, workspace),
        "packId": result.pack_id,
        "platformId": result.platform_id,
        "problems": result.problems,
        "solutionChecks": result.solution_checks,
    }


def build_problem_pack_bundle(
    workspace: Path,
    problem_ids: list[str],
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    solution_checks: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    """문제 팩 bundle에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_ids (list[str]): 문제 팩 bundle을 계산하거나 검증할 때 필요한 문제 ids 입력입니다.
        pack_id (str): 설치, 삭제, 조회할 문제 팩을 구분하는 ID입니다.
        output_dir (Path): 출력 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        platform_id (str | None): platform ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.
        verify_profile (str): 문제 팩 bundle을 계산하거나 검증할 때 필요한 verify 프로필 입력입니다.
        solution_checks (list[dict[str, object]] | None): 문제 팩 bundle을 계산하거나 검증할 때 필요한 솔루션 검사 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 팩 bundle 데이터입니다.
    """
    resolved_output_dir = output_dir if output_dir.is_absolute() else workspace / output_dir
    result = build_pack_for_problem_ids(
        problem_ids,
        pack_id,
        platform_id or current_platform_id(),
        resolved_output_dir,
        workspace,
        verify_profile,
        solution_checks=solution_checks,
        warmup_profile=SOLUTION_WARMUP_PROFILE,
    )
    return {
        "archivePath": str(result.archive_path),
        "archiveLabel": rel(result.archive_path, workspace),
        "packId": result.pack_id,
        "platformId": result.platform_id,
        "problems": result.problems,
        "solutionChecks": result.solution_checks,
    }
