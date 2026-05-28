"""show 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import argparse

from judge.core.artifacts import show


def handle(args: argparse.Namespace) -> int:
    """handle 함수를 실행하고 결과를 반환합니다.
    
    Args:
        args (argparse.Namespace): `args` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
    show(args.run_id, args.case_id, args.part)
    return 0
