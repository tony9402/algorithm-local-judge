from __future__ import annotations

import sys
from collections.abc import Sequence

from judge.cli_dispatch import COMMAND_HANDLERS, dispatch
from judge.cli_normalize import (
    RUN_GLOBAL_OPTIONS_WITH_VALUES,
    normalize_argv,
    run_global_command_error,
    run_global_option_name,
)
from judge.cli_parser import add_common_run_args, add_parser, build_parser
from judge.core.errors import JudgeError

__all__ = [
    "COMMAND_HANDLERS",
    "RUN_GLOBAL_OPTIONS_WITH_VALUES",
    "add_common_run_args",
    "add_parser",
    "build_parser",
    "dispatch",
    "main",
    "normalize_argv",
    "run_global_command_error",
    "run_global_option_name",
]


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint returning a process exit code."""
    parser = build_parser()
    explicit_argv = sys.argv[1:] if argv is None else argv
    try:
        args = parser.parse_args(normalize_argv(explicit_argv))
        result = dispatch(args, parser)
        return 0 if result is None else result
    except JudgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
