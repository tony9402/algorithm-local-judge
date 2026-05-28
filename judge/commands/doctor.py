"""환경 진단 CLI 명령의 인자 처리와 콘솔 출력을 담당합니다.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.pack import installed_packs
from judge.core.paths import (
    app_root,
    cache_root,
    current_platform_id,
    problem_pack_root,
    problem_source_root,
    repo_root,
    user_data_root,
)
from judge.core.remote_github import official_pack_repository

DOCTOR_SCHEMA_VERSION = 1
INSTALL_HINTS = {
    "cpp": (
        "Install Xcode Command Line Tools on macOS, build-essential on Linux, "
        "or MSYS2/MinGW on Windows."
    ),
    "javaCompiler": "Install a JDK and set ALJ_JAVAC when javac is not on PATH.",
    "javaRuntime": "Install a JDK/JRE and set ALJ_JAVA when java is not on PATH.",
    "git": "Install Git and make sure the git command is on PATH.",
}


def tool_status(
    label: str,
    candidates: list[str],
    env_name: str | None = None,
    hint_key: str | None = None,
) -> dict[str, Any]:
    """실행 파일 후보와 환경 변수 설정을 검사해 doctor 리포트에 넣을 도구 상태를 만듭니다.

    Args:
        label (str): 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
        candidates (list[str]): 도구 상태을 계산하거나 검증할 때 필요한 candidates 입력입니다.
        env_name (str | None): env 이름를 사용자 표시와 내부 조회에 함께 사용하는 이름입니다.
        hint_key (str | None): 도구 상태을 계산하거나 검증할 때 필요한 hint key 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 도구 상태 데이터입니다.
    """
    configured = os.environ.get(env_name) if env_name else None
    checked = [configured] if configured else candidates
    resolved = None
    for candidate in checked:
        if not candidate:
            continue
        if Path(candidate).is_absolute() and Path(candidate).exists():
            resolved = candidate
            break
        path = shutil.which(candidate)
        if path:
            resolved = path
            break
    return {
        "label": label,
        "status": "ok" if resolved else "missing",
        "path": resolved,
        "env": env_name,
        "configured": configured,
        "candidates": candidates,
        "installHint": INSTALL_HINTS.get(hint_key or label, ""),
    }


def path_status(label: str, path: Path) -> dict[str, Any]:
    """지정한 경로의 존재 여부와 디렉터리 여부를 doctor 리포트용 상태로 정리합니다.

    Args:
        label (str): 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 경로 상태 데이터입니다.
    """
    return {
        "label": label,
        "status": "ok" if path.exists() else "missing",
        "path": str(path),
        "exists": path.exists(),
        "isDir": path.is_dir(),
    }


def collect_diagnostics() -> dict[str, Any]:
    """로컬 플랫폼, 필수 도구, 데이터 경로, 설치된 문제팩 상태를 하나의 doctor 리포트로 수집합니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 진단 정보 데이터입니다.
    """
    packs = installed_packs()
    try:
        official_repository = official_pack_repository()
        official_repository_status = "ok"
        official_repository_error = None
    except JudgeError as exc:
        official_repository = None
        official_repository_status = "warning"
        official_repository_error = str(exc)
    tools = {
        "cpp": tool_status("C++ compiler", ["g++"], hint_key="cpp"),
        "javaCompiler": tool_status(
            "Java compiler",
            ["javac"],
            "ALJ_JAVAC",
            hint_key="javaCompiler",
        ),
        "javaRuntime": tool_status(
            "Java runtime",
            ["java"],
            "ALJ_JAVA",
            hint_key="javaRuntime",
        ),
        "git": tool_status("Git", ["git"], hint_key="git"),
    }
    paths = {
        "projectRoot": path_status("Project root", repo_root()),
        "appRoot": path_status("Application root", app_root()),
        "dataHome": path_status("Data home", user_data_root()),
        "cacheHome": path_status("Cache home", cache_root()),
        "packHome": path_status("Problem pack home", problem_pack_root()),
        "sourceHome": path_status("Problem source home", problem_source_root()),
    }
    required_statuses = [
        "ok",
        tools["cpp"]["status"],
        paths["projectRoot"]["status"],
        official_repository_status,
    ]
    status = "ok" if all(value == "ok" for value in required_statuses) else "warning"
    return {
        "schemaVersion": DOCTOR_SCHEMA_VERSION,
        "status": status,
        "platformId": current_platform_id(),
        "python": {
            "status": "ok",
            "path": sys.executable,
            "version": platform.python_version(),
        },
        "tools": tools,
        "paths": paths,
        "installedPacks": {
            "status": "ok",
            "count": len(packs),
            "packs": [
                {
                    "packId": pack.get("packId"),
                    "version": pack.get("version"),
                    "path": pack.get("path"),
                    "problems": pack.get("problems", []),
                }
                for pack in packs
            ],
        },
        "officialRepository": {
            "status": official_repository_status,
            "repository": official_repository,
            "error": official_repository_error,
        },
    }


def status_icon(status: str) -> str:
    """doctor 상태 문자열을 콘솔에 표시할 짧은 ASCII 표기로 바꿉니다.

    Args:
        status (str): 상태 icon을 계산하거나 검증할 때 필요한 상태 입력입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 상태 icon 문자열입니다.
    """
    return "OK" if status == "ok" else "WARN"


def print_text_report(diagnostics: dict[str, Any], verbose: bool) -> None:
    """doctor 진단 결과를 사람이 읽기 쉬운 콘솔 리포트로 출력합니다.

    Args:
        diagnostics (dict[str, Any]): print 텍스트 report을 계산하거나 검증할 때 필요한 진단 정보 입력입니다.
        verbose (bool): 상세 경로, 설치 힌트, 원본 설정을 출력에 포함할지 여부입니다.
    """
    print(f"Judge doctor: {diagnostics['status']}")
    print(f"Platform: {diagnostics['platformId']}")
    python = diagnostics["python"]
    print(f"Python: {status_icon(python['status'])} {python['version']} ({python['path']})")

    print("Tools:")
    for key in ("cpp", "javaCompiler", "javaRuntime", "git"):
        tool = diagnostics["tools"][key]
        value = tool["path"] or ", ".join(tool["candidates"])
        print(f"  {tool['label']}: {status_icon(tool['status'])} {value}")
        if tool["status"] != "ok" and tool.get("installHint"):
            print(f"    install: {tool['installHint']}")
        if verbose and tool.get("configured"):
            print(f"    configured by {tool['env']}: {tool['configured']}")

    print("Paths:")
    for key in ("projectRoot", "dataHome", "cacheHome", "packHome", "sourceHome"):
        path = diagnostics["paths"][key]
        print(f"  {path['label']}: {status_icon(path['status'])} {path['path']}")
        if verbose:
            print(f"    exists: {path['exists']}  dir: {path['isDir']}")

    installed = diagnostics["installedPacks"]
    print(f"Installed packs: {installed['count']}")
    if verbose and installed["packs"]:
        for pack in installed["packs"]:
            problems = ", ".join(pack.get("problems") or [])
            print(f"  {pack.get('packId')} {pack.get('version') or ''} problems: {problems}")
            if pack.get("path"):
                print(f"    {pack['path']}")

    official = diagnostics["officialRepository"]
    repository = official["repository"] or official["error"]
    print(f"Official repository: {status_icon(official['status'])} {repository}")


def handle(args: argparse.Namespace) -> int:
    """doctor CLI 명령의 옵션을 해석하고 필요한 서비스 호출과 출력 작업을 수행합니다.

    Args:
        args (argparse.Namespace): argparse가 파싱한 명령 옵션과 대상 값을 담은 네임스페이스입니다.

    Returns:
        int: 명령 성공 여부를 나타내는 프로세스 종료 코드입니다.
    """
    diagnostics = collect_diagnostics()
    if args.json:
        print(json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(diagnostics, args.verbose)
    return 0
