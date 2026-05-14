from __future__ import annotations

import argparse

from judge.web.server import run_server


def handle(args: argparse.Namespace) -> int:
    """Start the local web UI server."""
    run_server(args.host, args.port, args.open, args.debug)
    return 0
