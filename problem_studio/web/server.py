from __future__ import annotations

import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from problem_studio.web.app import create_app


def open_browser_later(url: str) -> None:
    """Open a browser shortly after the local server starts."""

    def worker() -> None:
        time.sleep(0.7)
        webbrowser.open(url)

    threading.Thread(target=worker, daemon=True).start()


def run_server(
    workspace: Path,
    host: str,
    port: int,
    open_browser: bool = False,
) -> None:
    """Run the local problem authoring web server."""
    url = f"http://{host}:{port}"
    if host not in {"127.0.0.1", "localhost"}:
        print(f"warning: binding to non-local host {host}; use only on trusted networks")
    print(f"Problem Studio running at {url}")
    print(f"Workspace: {Path(workspace).expanduser().resolve()}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        open_browser_later(url)
    uvicorn.run(create_app(workspace), host=host, port=port, log_level="warning")
