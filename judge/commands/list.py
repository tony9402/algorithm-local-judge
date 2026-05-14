from __future__ import annotations

import argparse
import sys

from judge.core.errors import JudgeError
from judge.core.problem import discover_problem_ids, load_problem, validate_problem_sequence


def handle(args: argparse.Namespace) -> int:
    """List problems and optionally validate numbering."""
    problem_ids = discover_problem_ids()
    if not problem_ids:
        print("No problems found.")
    else:
        print("Problems:")
        for problem_id in problem_ids:
            _, _, metadata = load_problem(problem_id)
            print(f"  {problem_id}  {metadata.get('title', '')}")

    if args.validate:
        errors = validate_problem_sequence(problem_ids)
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            raise JudgeError("problem numbering validation failed")
        print("Problem numbering is valid.")
    return 0
