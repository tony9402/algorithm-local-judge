"""cli 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from judge.core.errors import JudgeError
from problem_studio.commands.web import handle as handle_web


def build_parser() -> argparse.ArgumentParser:
    """build_parser 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        argparse.ArgumentParser: 처리 결과를 반환합니다.
    """
    parser = argparse.ArgumentParser(prog="problem-studio", allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command")

    web_parser = subparsers.add_parser("web", allow_abbrev=False)
    web_parser.add_argument("--workspace", default=".")
    web_parser.add_argument("--clone")
    web_parser.add_argument("--branch")
    web_parser.add_argument("--repo")
    web_parser.add_argument("--repo-name")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8775)
    web_open = web_parser.add_mutually_exclusive_group()
    web_open.add_argument("--open", dest="open", action="store_true", default=True)
    web_open.add_argument("--no-open", dest="open", action="store_false")

    return parser


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
    if args.command == "web":
        args.workspace = Path(args.workspace)
        return handle_web(args)
    raise JudgeError(f"unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    """main 함수를 실행하고 결과를 반환합니다.
    
    Args:
        argv (Sequence[str] | None): `argv` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
    parser = build_parser()
    explicit_argv = sys.argv[1:] if argv is None else argv
    try:
        return dispatch(parser.parse_args(explicit_argv), parser)
    except JudgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
