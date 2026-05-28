"""서버 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
"""
from __future__ import annotations

import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from problem_studio.web.app import create_app
from problem_studio.web.security_policy import is_local_binding


def open_browser_later(url: str) -> None:
    """browser later 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.

    Args:
        url (str): 브라우저 또는 Git 명령에 전달할 URL입니다.
    """

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
    """서버 실행에 필요한 입력을 준비하고 외부 프로세스나 서비스 호출을 수행합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        host (str): 서버을 계산하거나 검증할 때 필요한 host 입력입니다.
        port (int): 서버을 계산하거나 검증할 때 필요한 port 입력입니다.
        open_browser (bool): 서버 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        active_repository (str | None): 서버을 계산하거나 검증할 때 필요한 활성 저장소 입력입니다.
    """
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
