"""케이스 CLI 명령의 인자 처리와 콘솔 출력을 담당합니다."""

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
    """컴파일 명령이나 이벤트를 받아 필요한 검증과 서비스 호출을 수행합니다.

    Args:
        args (argparse.Namespace): argparse가 파싱한 명령 옵션과 대상 값을 담은 네임스페이스입니다.
    """
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
    """cases CLI 명령의 옵션을 해석하고 필요한 서비스 호출과 출력 작업을 수행합니다.

    Args:
        args (argparse.Namespace): argparse가 파싱한 명령 옵션과 대상 값을 담은 네임스페이스입니다.

    Returns:
        int: 명령 성공 여부를 나타내는 프로세스 종료 코드입니다.
    """
    if args.cases_command == "compile":
        return handle_compile(args)
    raise JudgeError(f"unknown cases command: {args.cases_command}")
