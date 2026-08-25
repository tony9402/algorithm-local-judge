"""Judge CLI에서 Problem Studio를 같은 런타임으로 실행하는 명령입니다."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from alj_core.studio_cli_options import DEFAULT_STUDIO_WEB_PORT
from judge.core.errors import JudgeError


def resolve_studio_executable() -> Path:
    """현재 설치와 PATH에서 Problem Studio 호환 실행기를 찾습니다."""
    suffix = ".exe" if sys.platform == "win32" else ""
    sibling = Path(sys.argv[0]).resolve().with_name(f"problem-studio{suffix}")
    if sibling.is_file():
        return sibling
    discovered = shutil.which("problem-studio")
    if discovered:
        return Path(discovered)
    raise JudgeError("problem-studio executable is missing from this installation")


def studio_argv(args: argparse.Namespace) -> list[str]:
    """Judge의 Studio 옵션을 기존 Problem Studio CLI 인자로 변환합니다."""
    command = ["web"]
    if action := getattr(args, "web_action", None):
        command.append(action)
    command.extend(["--workspace", str(args.workspace)])
    for option, attribute in [
        ("--clone", "clone"),
        ("--branch", "branch"),
        ("--repo", "repo"),
        ("--repo-name", "repo_name"),
        ("--host", "host"),
    ]:
        value = getattr(args, attribute, None)
        if value:
            command.extend([option, str(value)])
    command.extend(["--port", str(args.port or DEFAULT_STUDIO_WEB_PORT)])
    if getattr(args, "allow_remote_write", False):
        command.append("--allow-remote-write")
    command.append("--open" if args.open else "--no-open")
    return command


def handle(args: argparse.Namespace) -> int:
    """`judge studio` 옵션을 Problem Studio 웹 명령에 전달합니다.

    Args:
        args (argparse.Namespace): Studio 작업공간과 웹 서버 옵션입니다.

    Returns:
        int: Problem Studio 웹 명령의 종료 코드입니다.
    """
    executable = resolve_studio_executable()
    result = subprocess.run([str(executable), *studio_argv(args)], check=False)
    return result.returncode
