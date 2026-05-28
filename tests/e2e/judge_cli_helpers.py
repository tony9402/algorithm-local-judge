"""judge 명령줄 종단 간 테스트가 격리된 런타임에서 명령을 실행하고 결과 산출물을 찾도록 돕는 모듈입니다."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUDGE_COMMAND = [sys.executable, "-m", "judge"]


def judge_env(runtime: Path, *, project_root: Path | None = None) -> dict[str, str]:
    """judge 명령줄 테스트가 사용자 홈과 캐시를 오염시키지 않도록 격리된 환경 변수를 구성합니다.

    Args:
        runtime (Path): 격리된 데이터 홈과 캐시 홈을 담은 런타임 디렉터리입니다.
        project_root (Path | None): judge 명령을 실행할 프로젝트 루트 경로입니다.

    Returns:
        dict[str, str]: judge 명령줄 테스트에 사용할 환경 변수 사전입니다.
    """
    return {
        **os.environ,
        "ALJ_CACHE_HOME": str(runtime / "cache"),
        "ALJ_DATA_HOME": str(runtime / "data"),
        "ALJ_PACK_HOME": str(runtime / "packs"),
        "ALJ_SOURCE_HOME": str(runtime / "sources"),
        "ALJ_PROJECT_ROOT": str(project_root) if project_root is not None else str(ROOT),
        "ALJ_PYTHON": sys.executable,
    }


def run_judge_cli(
    runtime: Path,
    *args: str,
    check: bool = False,
    project_root: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """judge 명령을 격리된 환경에서 실행하고 표준 출력, 표준 오류, 종료 코드를 함께 돌려줍니다.

    Args:
        runtime (Path): 격리된 데이터 홈과 캐시 홈을 담은 런타임 디렉터리입니다.
        args (str): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
        check (bool): 하위 프로세스 실패를 예외로 처리할지 결정하는 플래그입니다.
        project_root (Path | None): judge 명령을 실행할 프로젝트 루트 경로입니다.
        extra_env (dict[str, str] | None): 격리 실행 환경에 추가로 주입할 환경 변수입니다.

    Returns:
        subprocess.CompletedProcess[str]: 격리된 환경에서 실행한 judge 명령줄 결과 객체입니다.
    """
    env = judge_env(runtime, project_root=project_root)
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [*JUDGE_COMMAND, *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        command = " ".join([*JUDGE_COMMAND, *args])
        raise AssertionError(
            f"command failed: {command}\n"
            f"returncode: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def run_dir_from_stdout(runtime: Path, stdout: str) -> Path:
    """judge 실행 출력에서 산출물 디렉터리 위치를 찾아 후속 조회 테스트에 전달합니다.

    Args:
        runtime (Path): 격리된 데이터 홈과 캐시 홈을 담은 런타임 디렉터리입니다.
        stdout (str): 명령 실행 결과에서 추출한 표준 출력 문자열입니다.

    Returns:
        Path: 명령 출력에서 추출한 실행 산출물 디렉터리 경로입니다.
    """
    match = re.search(r"run:\s+(.+)", stdout)
    if not match:
        raise AssertionError(f"run directory not found in stdout:\n{stdout}")
    label = match.group(1).strip()
    path = Path(label)
    if not path.is_absolute():
        path = runtime / "cache" / path
    return path


def assert_cli_failed(test: unittest.TestCase, result: subprocess.CompletedProcess[str]) -> None:
    """실패해야 하는 명령이 성공했을 때 표준 출력과 표준 오류를 포함해 테스트를 실패시킵니다.

    Args:
        test (unittest.TestCase): 검증 실패를 보고할 테스트 케이스 인스턴스입니다.
        result (subprocess.CompletedProcess[str]): 완료된 작업 응답에 포함할 결과 페이로드입니다.
    """
    test.assertNotEqual(
        result.returncode,
        0,
        f"command unexpectedly succeeded\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
    )


def write_trivial_python_source(target: Path) -> Path:
    """항상 통과하는 최소 Python 제출 파일을 작성해 실행 흐름 자체를 검증할 수 있게 합니다.

    Args:
        target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.

    Returns:
        Path: 테스트가 생성하거나 조회한 파일 시스템 경로입니다.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('ok')\n", encoding="utf-8")
    return target
