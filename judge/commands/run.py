"""실행 CLI 명령의 인자 처리와 콘솔 출력을 담당합니다."""

from __future__ import annotations

import argparse

from judge.core.submission import run_submission


def handle(args: argparse.Namespace) -> int:
    """run CLI 명령의 옵션을 해석하고 필요한 서비스 호출과 출력 작업을 수행합니다.

    Args:
        args (argparse.Namespace): argparse가 파싱한 명령 옵션과 대상 값을 담은 네임스페이스입니다.

    Returns:
        int: 명령 성공 여부를 나타내는 프로세스 종료 코드입니다.
    """
    run_submission(
        args.code_file,
        args.run_problem or args.problem,
        args.run_profile or args.profile,
        language=args.run_language or args.language,
    )
    return 0
