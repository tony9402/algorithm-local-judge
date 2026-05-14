from __future__ import annotations

import os
import threading
import time
import webbrowser

import uvicorn

from judge.web.app import create_app


def open_browser_later(url: str) -> None:
    """Open a browser shortly after the local server starts."""

    def worker() -> None:
        """Delay browser opening until Uvicorn has started binding."""
        time.sleep(0.7)
        webbrowser.open(url)

    threading.Thread(target=worker, daemon=True).start()


def run_server(host: str, port: int, open_browser: bool = False, debug: bool = False) -> None:
    """Run the local FastAPI web server."""
    url = f"http://{host}:{port}"
    if host not in {"127.0.0.1", "localhost"}:
        print(f"warning: binding to non-local host {host}; use only on trusted networks")
    if debug:
        os.environ["ALJ_WEB_DEBUG"] = "1"
    print(f"Local judge UI running at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        open_browser_later(url)
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
