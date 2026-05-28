"""web 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import argparse

from problem_studio.core.repositories import clone_problem_repository
from problem_studio.web.server import run_server


def handle(args: argparse.Namespace) -> int:
    """handle 함수를 실행하고 결과를 반환합니다.
    
    Args:
        args (argparse.Namespace): `args` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
    active_repository = args.repo
    if args.clone:
        summary = clone_problem_repository(args.workspace, args.clone, args.branch, args.repo_name)
        active_repository = summary["name"]
    run_server(args.workspace, args.host, args.port, args.open, active_repository)
    return 0
