"""Problem Studio Docker 명령을 함께 설치된 Judge 실행기에 전달합니다."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from alj_core.errors import JudgeError


def resolve_judge_executable() -> Path:
    """현재 설치와 PATH에서 함께 설치된 Judge 실행기를 찾습니다."""
    suffix = ".exe" if sys.platform == "win32" else ""
    sibling = Path(sys.argv[0]).resolve().with_name(f"judge{suffix}")
    if sibling.is_file():
        return sibling
    discovered = shutil.which("judge")
    if discovered:
        return Path(discovered)
    raise JudgeError("judge executable is missing from this installation")


def docker_argv(args: argparse.Namespace) -> list[str]:
    """Problem Studio 옵션을 공용 Judge Docker 하위 명령 인자로 변환합니다."""
    command = ["docker", "studio"]
    if args.docker_web_action:
        command.append(args.docker_web_action)
    if args.workspace is not None:
        command.extend(["--workspace", str(args.workspace)])
    if args.port is not None:
        command.extend(["--port", str(args.port)])
    return command


def handle(args: argparse.Namespace) -> int:
    executable = resolve_judge_executable()
    result = subprocess.run([str(executable), *docker_argv(args)], check=False)
    return result.returncode


__all__ = ["docker_argv", "handle", "resolve_judge_executable"]
