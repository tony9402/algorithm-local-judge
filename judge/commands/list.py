"""목록 CLI 명령의 인자 처리와 콘솔 출력을 담당합니다."""

from __future__ import annotations

import argparse
import sys

from judge.core.errors import JudgeError
from judge.core.paths import repo_root
from judge.core.problem import discover_problem_ids, load_problem, validate_problem_sequence


def handle(args: argparse.Namespace) -> int:
    """list CLI 명령의 옵션을 해석하고 필요한 서비스 호출과 출력 작업을 수행합니다.

    Args:
        args (argparse.Namespace): argparse가 파싱한 명령 옵션과 대상 값을 담은 네임스페이스입니다.

    Returns:
        int: 명령 성공 여부를 나타내는 프로세스 종료 코드입니다.
    """
    problem_ids = discover_problem_ids()
    if not problem_ids:
        print("No problems found.")
    else:
        print("Problems:")
        for problem_id in problem_ids:
            _, _, metadata = load_problem(problem_id)
            print(f"  {problem_id}  {metadata.get('title', '')}")

    if args.validate:
        validation_problem_ids = discover_problem_ids(repo_root())
        errors = validate_problem_sequence(validation_problem_ids)
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            raise JudgeError("problem numbering validation failed")
        print("Problem numbering is valid.")
    return 0
