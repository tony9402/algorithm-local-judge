from __future__ import annotations

import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from problem_studio.web.app import create_app
from problem_studio.web.security_policy import is_local_binding


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
    active_repository: str | None = None,
) -> None:
    """Run the local problem authoring web server."""
    url = f"http://{host}:{port}"
    local_binding = is_local_binding(host)
    if not local_binding:
        print(f"warning: binding to non-local host {host}; use only on trusted networks")
    print(f"Problem Studio running at {url}")
    print(f"Workspace: {Path(workspace).expanduser().resolve()}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        open_browser_later(url)
    git_write_enabled = local_binding
    uvicorn.run(
        create_app(
            workspace,
            active_repository=active_repository,
            local_binding=local_binding,
            git_write_enabled=git_write_enabled,
            workspace_write_enabled=local_binding,
            workspace_warning=not local_binding,
        ),
        host=host,
        port=port,
        log_level="warning",
    )
