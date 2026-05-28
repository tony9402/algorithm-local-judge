"""cli_dispatch 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import argparse

from judge.commands import cache as cache_command
from judge.commands import cases as cases_command
from judge.commands import compile as compile_command
from judge.commands import diff as diff_command
from judge.commands import doctor as doctor_command
from judge.commands import generate as generate_command
from judge.commands import list as list_command
from judge.commands import pack as pack_command
from judge.commands import problem as problem_command
from judge.commands import run as run_command
from judge.commands import show as show_command
from judge.commands import web as web_command
from judge.core.errors import JudgeError

COMMAND_HANDLERS = {
    "compile": compile_command.handle,
    "cases": cases_command.handle,
    "list": list_command.handle,
    "doctor": doctor_command.handle,
    "generate": generate_command.handle,
    "run": run_command.handle,
    "show": show_command.handle,
    "diff": diff_command.handle,
    "cache": cache_command.handle,
    "pack": pack_command.handle,
    "problem": problem_command.handle,
    "web": web_command.handle,
}


def dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """dispatch 함수를 실행하고 결과를 반환합니다.
    
    Args:
        args (argparse.Namespace): `args` 값입니다.
        parser (argparse.ArgumentParser): `parser` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
    if args.command is None:
        parser.print_help()
        return 1

    try:
        handler = COMMAND_HANDLERS[args.command]
    except KeyError as exc:
        raise JudgeError(f"unknown command: {args.command}") from exc
    return handler(args)
