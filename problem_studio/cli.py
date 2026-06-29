"""CLI 기능을 담당하는 모듈입니다.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from alj_core.errors import JudgeError
from problem_studio.commands.web import handle as handle_web


def build_parser() -> argparse.ArgumentParser:
    """parser에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Returns:
        argparse.ArgumentParser: 공통 옵션과 하위 명령이 등록된 argparse 파서입니다.
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
    """파싱된 하위 명령 이름을 등록된 핸들러에 연결하고 명령이 없으면 도움말을 출력합니다.

        Args:
            args (argparse.Namespace): argparse가 파싱한 명령 옵션과 대상 값을 담은 네임스페이스입니다.
            parser (argparse.ArgumentParser): 하위 명령과 공통 옵션을 등록하거나 오류를 출력할 argparse 파서입니다.
    """
    if args.command is None:
        parser.print_help()
        return 1
    if args.command == "web":
        args.workspace = Path(args.workspace)
        return handle_web(args)
    raise JudgeError(f"unknown command: {args.command}")


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
        return dispatch(parser.parse_args(explicit_argv), parser)
    except JudgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
