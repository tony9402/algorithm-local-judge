"""문제 스튜디오 종단 간 테스트가 외부 컴파일러와 빌드 도구 없이 결정적인 결과를 받도록 가짜 실행기를 제공하는 모듈입니다."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from tests.e2e.helpers import create_runnable_minimal_pack


def fake_compile_problem_tools(
    problem_id: str,
    root: Path | None = None,
    **_kwargs,
) -> dict[str, Path]:
    """실제 컴파일 문제 도구 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
        root (Path | None): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.
        _kwargs (dict[str, Any]): 테스트 대역이 실제 함수 시그니처와 호환되도록 받는 사용하지 않는 키워드 인자입니다.

    Returns:
        dict[str, Path]: 호출자가 비교하거나 다음 명령에 전달할 문자열입니다.
    """
    workspace = Path(root or ".").resolve()
    target = workspace / ".judge-cache" / "e2e-tools" / problem_id
    target.mkdir(parents=True, exist_ok=True)
    tools = {}
    for name in ["generator", "validator", "checker", "solution"]:
        path = target / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
        tools[name] = path
    return tools


def fake_validate_all_data(
    workspace: Path,
    problem_id: str,
    force: bool = False,
    progress=None,
    **_kwargs,
) -> dict:
    """실제 검증 전체 데이터 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        workspace (Path): 문제 스튜디오나 패키지 작업을 수행할 임시 작업공간입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
        force (bool): 캐시나 기존 산출물을 무시하고 다시 처리할지 결정하는 플래그입니다.
        progress (Any): 가짜 실행기가 진행 로그를 전달할 콜백입니다.
        _kwargs (dict[str, Any]): 테스트 대역이 실제 함수 시그니처와 호환되도록 받는 사용하지 않는 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    if progress is not None:
        progress("Compiling cases.yml for all profiles.")
        progress("Validating generated case sample_1 (1/1).")
        progress("Validating generated case hidden_1 (1/2).")
        progress("Validating generated case hidden_2 (2/2).")
    return {
        "problemId": problem_id,
        "profileCount": 2,
        "caseCount": 3,
        "profiles": [
            {"name": "sample", "caseCount": 1},
            {"name": "hidden", "caseCount": 2},
        ],
        "force": force,
    }


def fake_verify_solutions(
    workspace: Path,
    problem_id: str,
    profile: str = "hidden",
    progress=None,
    **_kwargs,
) -> dict:
    """실제 검증 솔루션 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        workspace (Path): 문제 스튜디오나 패키지 작업을 수행할 임시 작업공간입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
        profile (str): 검증이나 실행에 사용할 테스트 프로필 이름입니다.
        progress (Any): 가짜 실행기가 진행 로그를 전달할 콜백입니다.
        _kwargs (dict[str, Any]): 테스트 대역이 실제 함수 시그니처와 호환되도록 받는 사용하지 않는 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    paths = _kwargs.get("solutions")
    if not paths:
        solution_dir = workspace / "problems" / problem_id / "solutions"
        paths = [
            path.relative_to(workspace / "problems" / problem_id).as_posix()
            for path in sorted(solution_dir.glob("*"))
        ] or ["solutions/main_solution.ac.cpp"]
    if progress is not None:
        progress(f"Running solution checks for {problem_id}.")
    return {
        "problemId": problem_id,
        "profile": profile,
        "passed": True,
        "verifiedCount": len(paths),
        "totalCount": len(paths),
        "skippedCount": 0,
        "checks": [
            {
                "path": path,
                "sourcePath": path,
                "expectedStatus": "accepted",
                "actualStatus": "accepted",
                "passed": True,
                "runId": "e2e-run",
                "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
                "cases": [
                    {
                        "case": "hidden-1",
                        "status": "accepted",
                        "timeMs": 1,
                        "memoryBytes": 1024,
                    }
                ],
            }
            for path in paths
        ],
    }


def fake_build_problem_pack(
    workspace: Path,
    problem_id: str,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    **_kwargs,
) -> dict:
    """실제 빌드 문제 패키지 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        workspace (Path): 문제 스튜디오나 패키지 작업을 수행할 임시 작업공간입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
        pack_id (str): 생성하거나 설치할 테스트 패키지 식별자입니다.
        output_dir (Path): 패키지 산출물을 기록할 작업공간 기준 디렉터리입니다.
        platform_id (str | None): 패키지 빌드 대상 플랫폼 식별자입니다.
        verify_profile (str): 패키지 빌드 전에 검증할 테스트 프로필 이름입니다.
        _kwargs (dict[str, Any]): 테스트 대역이 실제 함수 시그니처와 호환되도록 받는 사용하지 않는 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    archive = workspace / output_dir / f"{pack_id}-e2e.aljpack"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"e2e-pack")
    return {
        "archivePath": str(archive),
        "archiveLabel": str(archive.relative_to(workspace)),
        "packId": pack_id,
        "platformId": platform_id or "e2e-platform",
        "verifyProfile": verify_profile,
        "problems": [problem_id],
        "solutionChecks": [],
    }


def fake_build_runnable_pack(
    workspace: Path,
    problem_id: str,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    **_kwargs,
) -> dict:
    """실제 빌드 실행 가능 패키지 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        workspace (Path): 문제 스튜디오나 패키지 작업을 수행할 임시 작업공간입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
        pack_id (str): 생성하거나 설치할 테스트 패키지 식별자입니다.
        output_dir (Path): 패키지 산출물을 기록할 작업공간 기준 디렉터리입니다.
        platform_id (str | None): 패키지 빌드 대상 플랫폼 식별자입니다.
        verify_profile (str): 패키지 빌드 전에 검증할 테스트 프로필 이름입니다.
        _kwargs (dict[str, Any]): 테스트 대역이 실제 함수 시그니처와 호환되도록 받는 사용하지 않는 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    archive = workspace / output_dir / f"{pack_id}-{problem_id}-e2e.aljpack"
    create_runnable_minimal_pack(archive, pack_id=pack_id, problem_id=problem_id)
    return {
        "archivePath": str(archive),
        "archiveLabel": str(archive.relative_to(workspace)),
        "packId": pack_id,
        "platformId": platform_id or "e2e-platform",
        "verifyProfile": verify_profile,
        "problems": [problem_id],
        "solutionChecks": [],
    }


def fake_slow_build_runnable_pack(*args, **kwargs) -> dict:
    """실제 느린 빌드 실행 가능 패키지 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
        kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    time.sleep(2.0)
    return fake_build_runnable_pack(*args, **kwargs)


def fake_cancellable_slow_build_runnable_pack(*args, cancel_token=None, **kwargs) -> dict:
    """실제 취소 가능 느린 빌드 실행 가능 패키지 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
        cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.
        kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    for _ in range(150):
        if cancel_token:
            cancel_token.check()
        time.sleep(0.1)
    return fake_build_runnable_pack(*args, **kwargs)


def fake_verify_solutions_mismatch(
    workspace: Path,
    problem_id: str,
    profile: str = "hidden",
    progress=None,
    **_kwargs,
) -> dict:
    """실제 검증 솔루션 불일치 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        workspace (Path): 문제 스튜디오나 패키지 작업을 수행할 임시 작업공간입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
        profile (str): 검증이나 실행에 사용할 테스트 프로필 이름입니다.
        progress (Any): 가짜 실행기가 진행 로그를 전달할 콜백입니다.
        _kwargs (dict[str, Any]): 테스트 대역이 실제 함수 시그니처와 호환되도록 받는 사용하지 않는 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    result = fake_verify_solutions(workspace, problem_id, profile, progress, **_kwargs)
    result["passed"] = False
    if result["checks"]:
        result["checks"][0] = {
            **result["checks"][0],
            "actualStatus": "wrong_answer",
            "passed": False,
            "message": "forced mismatch",
        }
    return result


def fake_bulk_build(
    workspace: Path,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    force: bool = False,
    progress=None,
    max_workers: int | None = None,
    problem_ids: list[str] | None = None,
    **_kwargs,
) -> dict:
    """실제 일괄 빌드 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        workspace (Path): 문제 스튜디오나 패키지 작업을 수행할 임시 작업공간입니다.
        pack_id (str): 생성하거나 설치할 테스트 패키지 식별자입니다.
        output_dir (Path): 패키지 산출물을 기록할 작업공간 기준 디렉터리입니다.
        platform_id (str | None): 패키지 빌드 대상 플랫폼 식별자입니다.
        verify_profile (str): 패키지 빌드 전에 검증할 테스트 프로필 이름입니다.
        force (bool): 캐시나 기존 산출물을 무시하고 다시 처리할지 결정하는 플래그입니다.
        progress (Any): 가짜 실행기가 진행 로그를 전달할 콜백입니다.
        max_workers (int | None): 일괄 빌드에서 동시에 사용할 작업자 수입니다.
        problem_ids (list[str] | None): 일괄 작업에서 처리할 문제 식별자 목록입니다.
        _kwargs (dict[str, Any]): 테스트 대역이 실제 함수 시그니처와 호환되도록 받는 사용하지 않는 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    ids = problem_ids or ["alpha"]
    if progress is not None:
        for index, problem_id in enumerate(ids, start=1):
            progress(f"[{index}/{len(ids)}] Problem {problem_id}: Pack built: {pack_id}")
    return {
        "passed": True,
        "summary": f"{len(ids)}개 문제 전체 테스트 통과 · 1개 팩 생성",
        "problemCount": len(ids),
        "failedCount": 0,
        "packCount": 1,
        "force": force,
        "maxWorkers": max_workers,
        "verifyProfile": verify_profile,
        "platformId": platform_id or "e2e-platform",
        "problems": [
            {
                "problemId": problem_id,
                "passed": True,
                "summary": "ok",
                "pack": {"archiveLabel": f"dist/packs/{pack_id}-e2e.aljpack"},
            }
            for problem_id in ids
        ],
    }


def fake_slow_bulk_build(*args, cancel_token=None, **kwargs) -> dict:
    """실제 느린 일괄 빌드 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
        cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.
        kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    if cancel_token:
        cancel_token.check()
    time.sleep(2.0)
    if cancel_token:
        cancel_token.check()
    return fake_bulk_build(*args, **kwargs)


def fake_cancellable_slow_bulk_build(*args, cancel_token=None, **kwargs) -> dict:
    """실제 취소 가능 느린 일괄 빌드 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
        cancel_token (Any): 장시간 작업을 중단할 수 있는 취소 토큰입니다.
        kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    for _ in range(150):
        if cancel_token:
            cancel_token.check()
        time.sleep(0.1)
    return fake_bulk_build(*args, **kwargs)


def fake_bulk_build_partial(
    workspace: Path,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    force: bool = False,
    progress=None,
    max_workers: int | None = None,
    problem_ids: list[str] | None = None,
    **_kwargs,
) -> dict:
    """실제 일괄 빌드 부분 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

    Args:
        workspace (Path): 문제 스튜디오나 패키지 작업을 수행할 임시 작업공간입니다.
        pack_id (str): 생성하거나 설치할 테스트 패키지 식별자입니다.
        output_dir (Path): 패키지 산출물을 기록할 작업공간 기준 디렉터리입니다.
        platform_id (str | None): 패키지 빌드 대상 플랫폼 식별자입니다.
        verify_profile (str): 패키지 빌드 전에 검증할 테스트 프로필 이름입니다.
        force (bool): 캐시나 기존 산출물을 무시하고 다시 처리할지 결정하는 플래그입니다.
        progress (Any): 가짜 실행기가 진행 로그를 전달할 콜백입니다.
        max_workers (int | None): 일괄 빌드에서 동시에 사용할 작업자 수입니다.
        problem_ids (list[str] | None): 일괄 작업에서 처리할 문제 식별자 목록입니다.
        _kwargs (dict[str, Any]): 테스트 대역이 실제 함수 시그니처와 호환되도록 받는 사용하지 않는 키워드 인자입니다.

    Returns:
        dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
    """
    ids = problem_ids or ["alpha", "beta"]
    if progress is not None:
        for index, problem_id in enumerate(ids, start=1):
            status = "Pack built" if index == 1 else "Full test failed"
            progress(f"[{index}/{len(ids)}] Problem {problem_id}: {status}: forced")
    return {
        "passed": False,
        "summary": f"{len(ids)}개 중 1개 문제 실패 · 1개 팩 생성",
        "problemCount": len(ids),
        "failedCount": 1,
        "packCount": 1,
        "force": force,
        "maxWorkers": max_workers,
        "verifyProfile": verify_profile,
        "platformId": platform_id or "e2e-platform",
        "problems": [
            {
                "problemId": problem_id,
                "passed": index == 0,
                "summary": "ok" if index == 0 else "forced failure",
                "pack": (
                    {"archiveLabel": f"dist/packs/{pack_id}-{problem_id}.aljpack"}
                    if index == 0
                    else None
                ),
            }
            for index, problem_id in enumerate(ids)
        ],
    }


def git(cwd: Path, *args: str) -> str:
    """테스트 저장소 안에서 Git 명령을 실행하고 실패 시 표준 오류를 포함해 즉시 실패시킵니다.

    Args:
        cwd (Path): Git 또는 명령줄 도구를 실행할 작업 디렉터리입니다.
        args (str): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.

    Returns:
        str: Git 명령의 표준 출력에서 앞뒤 공백을 제거한 문자열입니다.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()
