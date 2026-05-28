"""generate 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import argparse

from judge.core.generation import generate


def handle(args: argparse.Namespace) -> int:
    """handle 함수를 실행하고 결과를 반환합니다.
    
    Args:
        args (argparse.Namespace): `args` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
    generate(args.problem, args.profile, args.force)
    return 0
