"""judge CLI의 인자 정규화, 파싱, 명령 디스패치를 묶어 제공하는 진입점입니다."""

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
    """CLI 인자를 정규화해 파싱하고 선택된 하위 명령의 종료 코드를 결정합니다.

    Args:
        argv (Sequence[str] | None): 프로그램 이름을 제외한 CLI 인자 목록입니다. None이면 현재 프로세스의 인자를 읽습니다.

    Returns:
        int: 명령 성공 여부를 나타내는 프로세스 종료 코드입니다.
    """
    parser = build_parser()
    explicit_argv = sys.argv[1:] if argv is None else argv
    try:
        args = parser.parse_args(normalize_argv(explicit_argv))
        result = dispatch(args, parser)
        return 0 if result is None else result
    except JudgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
