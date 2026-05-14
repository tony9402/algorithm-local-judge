from __future__ import annotations

import argparse

from judge.core.submission import run_submission


def handle(args: argparse.Namespace) -> int:
    """Compile and judge a submitted source file."""
    run_submission(
        args.code_file,
        args.run_problem or args.problem,
        args.run_profile or args.profile,
    )
    return 0
