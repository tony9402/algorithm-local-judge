from __future__ import annotations

import argparse

from judge.core.cache import build_cache_clear_plan, cache_status, delete_cache_targets
from judge.core.errors import JudgeError
from judge.core.paths import rel
from judge.utils.fs import path_size
from judge.utils.text import format_size


def handle(args: argparse.Namespace) -> int:
    """Handle `judge cache ...` subcommands."""
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
