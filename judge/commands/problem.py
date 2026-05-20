from __future__ import annotations

import argparse

from judge.core.errors import JudgeError
from judge.core.problem import discover_problem_ids, load_problem
from judge.core.remote import install_problem_source


def print_installed_problem_source(result: dict) -> None:
    """Print a concise success message for a problem install result."""
    print(f"Installed problem pack: {result.get('label') or result.get('installedPath')}")
    if repository := result.get("repository"):
        print(f"Repository: {repository}")
    if asset_name := result.get("assetName"):
        print(f"Asset: {asset_name}")
    if downloaded_path := result.get("downloadedPath"):
        print(f"Downloaded: {downloaded_path}")
    print("Run `judge list` to see installed problems.")


def handle(args: argparse.Namespace) -> int:
    """Handle easy `judge problem ...` commands."""
    if args.problem_command == "install":
        result = install_problem_source(args.source, args.asset)
        print_installed_problem_source(result)
        return 0

    if args.problem_command == "list":
        problem_ids = discover_problem_ids()
        if not problem_ids:
            print("No problems installed.")
            return 0
        print("Problems:")
        for problem_id in problem_ids:
            _, _, metadata = load_problem(problem_id)
            print(f"  {problem_id}  {metadata.get('title', '')}")
        return 0

    raise JudgeError(f"unknown problem command: {args.problem_command}")
