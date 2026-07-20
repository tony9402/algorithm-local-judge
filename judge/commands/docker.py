"""Signed Docker Judge launcher의 CLI 하위 명령을 처리합니다."""

from __future__ import annotations

import argparse

from judge.core.docker_launcher import run_docker_web, setup_docker_judge
from judge.core.errors import JudgeError


def handle(args: argparse.Namespace) -> int:
    """Docker setup 또는 hardened web launcher를 host fallback 없이 실행합니다."""
    if args.docker_command == "setup":
        setup_docker_judge()
        return 0
    if args.docker_command == "web":
        run_docker_web(args.port)
        return 0
    raise JudgeError(f"unknown docker command: {args.docker_command}")


__all__ = ["handle"]
