"""웹 CLI 명령의 인자 처리와 콘솔 출력을 담당합니다.
"""
from __future__ import annotations

import argparse

from problem_studio.core.repositories import clone_problem_repository
from problem_studio.web.server import run_server


def handle(args: argparse.Namespace) -> int:
    """web CLI 명령의 옵션을 해석하고 필요한 서비스 호출과 출력 작업을 수행합니다.

    Args:
        args (argparse.Namespace): argparse가 파싱한 명령 옵션과 대상 값을 담은 네임스페이스입니다.

    Returns:
        int: 명령 성공 여부를 나타내는 프로세스 종료 코드입니다.
    """
    active_repository = args.repo
    if args.clone:
        summary = clone_problem_repository(args.workspace, args.clone, args.branch, args.repo_name)
        active_repository = summary["name"]
    run_server(args.workspace, args.host, args.port, args.open, active_repository)
    return 0
