from __future__ import annotations

import argparse

from judge.core.generation import generate


def handle(args: argparse.Namespace) -> int:
    """Generate or reuse test data for one problem."""
    generate(args.problem, args.profile, args.force)
    return 0
