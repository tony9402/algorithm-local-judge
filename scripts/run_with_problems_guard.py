"""Run a command and always prove that the local problems tree stayed immutable."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from scripts.problems_tree_guard import verify_snapshot, write_snapshot
except ModuleNotFoundError:
    # Direct `python scripts/run_with_problems_guard.py` execution places only
    # scripts/ on sys.path, while module execution places the repository root.
    from problems_tree_guard import verify_snapshot, write_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("problems"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def main() -> int:
    args = parse_args()
    if not args.root.exists():
        print(f"Problems guard: {args.root} is absent; running isolated command.")
        return subprocess.run(args.command, check=False).returncode

    with tempfile.TemporaryDirectory(prefix="alj-problems-guard-") as tmp:
        snapshot = Path(tmp) / "snapshot.json"
        write_snapshot(args.root, snapshot)
        print(f"Problems guard: captured {args.root} before command.")
        try:
            return_code = subprocess.run(args.command, check=False).returncode
        finally:
            changes = verify_snapshot(args.root, snapshot)
        if changes:
            print(
                "ERROR: command modified problems/**; use a temporary isolated workspace.",
                file=sys.stderr,
            )
            for path in changes[:100]:
                print(f"  {path}", file=sys.stderr)
            if len(changes) > 100:
                print(f"  ... and {len(changes) - 100} more", file=sys.stderr)
            return 86
        print("Problems guard: verified no additions, modifications, or deletions.")
        return return_code


if __name__ == "__main__":
    raise SystemExit(main())
