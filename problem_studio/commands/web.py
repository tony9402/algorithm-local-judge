from __future__ import annotations

import argparse

from problem_studio.web.server import run_server


def handle(args: argparse.Namespace) -> int:
    """Start the problem authoring web server."""
    run_server(args.workspace, args.host, args.port, args.open)
    return 0
