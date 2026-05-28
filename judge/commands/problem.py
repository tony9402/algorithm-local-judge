from __future__ import annotations

import argparse

from judge.core.errors import JudgeError
from judge.core.problem import discover_problem_ids, load_problem
from judge.core.problem_install_policy import PACK_INSTALL_POLICY
from judge.core.remote import install_problem_source


def print_installed_problem_source(result: dict) -> None:
    """Print a concise success message for a problem install result."""
    install_type = result.get("installType") or "pack"
    label = "source package" if install_type == "source" else "problem pack"
    print(f"Installed {label}: {result.get('label') or result.get('installedPath')}")
    if install_type == "source":
        print("Install type: source fallback")
    else:
        print("Install type: pack (.aljpack)")
    if repository := result.get("repository"):
        print(f"Repository: {repository}")
    if ref := result.get("ref"):
        print(f"Ref: {ref}")
    if commit_sha := result.get("commitSha"):
        print(f"Commit: {commit_sha}")
    if asset_name := result.get("assetName"):
        print(f"Asset: {asset_name}")
    if result.get("trustedRepository"):
        print("Trusted repository: verified")
    if result.get("checksumVerified"):
        print(f"Checksum: verified ({result.get('checksumSource')})")
    if problem_count := result.get("problemCount"):
        print(f"Problems: {problem_count}")
    if downloaded_path := result.get("downloadedPath"):
        print(f"Downloaded: {downloaded_path}")
    if install_type == "source":
        print(f"Policy: {PACK_INSTALL_POLICY}")
    if trust_warning := result.get("trustWarning"):
        print(trust_warning)
    print("Run `judge list` to see installed problems.")


def handle(args: argparse.Namespace) -> int:
    """Handle easy `judge problem ...` commands."""
    if args.problem_command == "install":
        result = install_problem_source(
            args.source,
            args.asset,
            args.ref,
            args.checksum,
            args.checksum_url,
        )
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
