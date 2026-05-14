from __future__ import annotations

import argparse

from judge.core.compiler import compile_problem_tools


def handle(args: argparse.Namespace) -> int:
    """Compile all tools for one problem."""
    compile_problem_tools(args.problem)
    print(f"Compiled tools for problem {args.problem}")
    return 0
