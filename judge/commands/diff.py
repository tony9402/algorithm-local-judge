from __future__ import annotations

import argparse

from judge.core.artifacts import diff


def handle(args: argparse.Namespace) -> int:
    """Show a unified diff for a wrong-answer case."""
    diff(args.run_id, args.case_id)
    return 0
