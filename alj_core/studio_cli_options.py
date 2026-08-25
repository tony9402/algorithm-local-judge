"""Judge와 Problem Studio 진입점이 공유하는 웹 CLI 옵션입니다."""

from __future__ import annotations

import argparse

DEFAULT_STUDIO_WEB_PORT = 8775


def add_web_arguments(parser: argparse.ArgumentParser) -> None:
    """Problem Studio 웹 서버 옵션을 argparse parser에 추가합니다."""
    parser.add_argument(
        "web_action",
        nargs="?",
        choices=["start", "stop", "restart", "status"],
        help="run in the background, stop, restart, or inspect it; omit for foreground mode",
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--clone")
    parser.add_argument("--branch")
    parser.add_argument("--repo")
    parser.add_argument("--repo-name")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--allow-remote-write",
        action="store_true",
        help="allow workspace reads and writes on a non-local binding; trusted networks only",
    )
    web_open = parser.add_mutually_exclusive_group()
    web_open.add_argument("--open", dest="open", action="store_true", default=True)
    web_open.add_argument("--no-open", dest="open", action="store_false")
    parser.add_argument("--service-runner", help=argparse.SUPPRESS)


__all__ = ["DEFAULT_STUDIO_WEB_PORT", "add_web_arguments"]
