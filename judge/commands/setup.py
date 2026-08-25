"""One-command first-run setup for the local Judge web application."""

from __future__ import annotations

import argparse

from judge.commands.doctor import collect_diagnostics, print_text_report
from judge.commands.problem import print_installed_problem_source
from judge.core.errors import JudgeError
from judge.core.problem import discover_problem_ids
from judge.core.remote import install_problem_source
from judge.core.toolchains import deactivate_managed_toolchain, managed_provider_status
from judge.web.server import run_server


def print_next_steps() -> None:
    print("Local Judge is ready.")
    print("  Check: judge doctor --verbose")
    print("  Start: judge web start")


def configure_toolchain_mode(mode: str) -> None:
    if mode in {"auto", "none"}:
        return
    if mode == "system":
        deactivate_managed_toolchain()
        print("Toolchains: using validated ALJ_* overrides and system PATH.")
        return
    status = managed_provider_status()
    if status["status"] == "ok" and status.get("active"):
        active = status["active"]
        print(f"Toolchains: using managed profile {active['profileId']} {active['version']}.")
        return
    raise JudgeError(
        status.get("error")
        or "managed toolchain provider is not configured; no download was attempted"
    )


def handle(args: argparse.Namespace) -> int:
    """Inspect local prerequisites, install the first pack, and optionally start the web UI."""
    configure_toolchain_mode(getattr(args, "toolchains", "auto"))
    diagnostics = collect_diagnostics()
    print_text_report(diagnostics, verbose=args.verbose)
    if args.check_only:
        return 0

    problem_ids = discover_problem_ids()
    if not problem_ids and not args.no_install_problems:
        print(f"No problems are installed. Installing from {args.repository}...")
        result = install_problem_source(args.repository)
        print_installed_problem_source(result)
        problem_ids = discover_problem_ids()
    elif not problem_ids:
        print("No problems are installed. Run `judge problem install owner/name` when ready.")
    else:
        print(f"Installed problems: {len(problem_ids)}")

    if args.no_web:
        print_next_steps()
        return 0

    print(f"Starting the local Judge at http://127.0.0.1:{args.port}")
    run_server("127.0.0.1", args.port, not args.no_open, False, False)
    return 0


__all__ = ["handle", "print_next_steps"]
