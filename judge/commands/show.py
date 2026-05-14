from __future__ import annotations

import argparse

from judge.core.artifacts import show


def handle(args: argparse.Namespace) -> int:
    """Print saved artifacts for one wrong-answer case."""
    show(args.run_id, args.case_id, args.part)
    return 0
