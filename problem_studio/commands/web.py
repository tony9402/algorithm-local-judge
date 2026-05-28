from __future__ import annotations

import argparse

from problem_studio.core.repositories import clone_problem_repository
from problem_studio.web.server import run_server


def handle(args: argparse.Namespace) -> int:
    """Start the problem authoring web server."""
    active_repository = args.repo
    if args.clone:
        summary = clone_problem_repository(args.workspace, args.clone, args.branch, args.repo_name)
        active_repository = summary["name"]
    run_server(args.workspace, args.host, args.port, args.open, active_repository)
    return 0
