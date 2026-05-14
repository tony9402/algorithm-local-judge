from __future__ import annotations

import argparse
from pathlib import Path

from judge.core.cases_compile import (
    compile_cases_file,
    compile_problem_cases,
    format_compile_result,
    result_to_json,
)
from judge.core.errors import JudgeError


def handle_compile(args: argparse.Namespace) -> int:
    """Compile and validate a cases.yml file."""
    has_problem = args.problem is not None
    has_file = args.file is not None
    if has_problem == has_file:
        raise JudgeError("choose exactly one target: <problem> or --file <cases.yml>")
    if args.max_preview is not None and args.max_preview < 1:
        raise JudgeError("--max-preview must be greater than zero")

    if has_file:
        result = compile_cases_file(Path(args.file), args.profile)
    else:
        result = compile_problem_cases(args.problem, args.profile)

    if args.json:
        print(result_to_json(result), end="")
    else:
        print(format_compile_result(result, args.expanded, args.max_preview))
    return 0 if result.valid else 1


def handle(args: argparse.Namespace) -> int:
    """Handle `judge cases ...` subcommands."""
    if args.cases_command == "compile":
        return handle_compile(args)
    raise JudgeError(f"unknown cases command: {args.cases_command}")
