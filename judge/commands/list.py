"""list 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import argparse
import sys

from judge.core.errors import JudgeError
from judge.core.paths import repo_root
from judge.core.problem import discover_problem_ids, load_problem, validate_problem_sequence


def handle(args: argparse.Namespace) -> int:
    """handle 함수를 실행하고 결과를 반환합니다.
    
    Args:
        args (argparse.Namespace): `args` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
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
