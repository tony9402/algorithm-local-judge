"""캐시 CLI 명령의 인자 처리와 콘솔 출력을 담당합니다.
"""
from __future__ import annotations

import argparse

from judge.core.cache import build_cache_clear_plan, cache_status, delete_cache_targets
from judge.core.errors import JudgeError
from judge.core.paths import rel
from judge.utils.fs import path_size
from judge.utils.text import format_size


def handle(args: argparse.Namespace) -> int:
    """cache CLI 명령의 옵션을 해석하고 필요한 서비스 호출과 출력 작업을 수행합니다.

    Args:
        args (argparse.Namespace): argparse가 파싱한 명령 옵션과 대상 값을 담은 네임스페이스입니다.

    Returns:
        int: 명령 성공 여부를 나타내는 프로세스 종료 코드입니다.
    """
    if args.cache_command == "status":
        cache_status()
        return 0
    if args.cache_command == "clear":
        if not (args.problem or args.runs or args.all):
            raise JudgeError("choose at least one target: --problem, --runs, or --all")
        plan = build_cache_clear_plan(
            problem=args.problem,
            profile=args.profile,
            runs=args.runs,
            all_entries=args.all,
        )
        if not plan.targets:
            print("No cache entries matched.")
            return 0
        print("Targets:")
        for path in plan.targets:
            print(f"  {rel(path, plan.root)} ({format_size(path_size(path))})")
        print(f"Total: {format_size(plan.total_size)}")
        if args.dry_run:
            print("Dry run: no files deleted.")
            return 0
        if args.all and not args.yes:
            answer = input("Delete all cache entries? Type 'yes' to continue: ")
            if answer != "yes":
                print("Cancelled.")
                return 0
        delete_cache_targets(plan.targets, plan.operation_root)
        print("Cache cleared.")
        return 0
    raise JudgeError(f"unknown cache command: {args.cache_command}")
