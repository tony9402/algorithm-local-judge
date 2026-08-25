"""서버 웹 백엔드 구성과 응답 데이터 조립을 담당합니다."""

from __future__ import annotations

import os
import threading
import time
import webbrowser

import uvicorn

from commons.job_persistence import default_job_history_path
from judge.core.docker_runtime import SANDBOX_MODE_ENV, ensure_sandbox_preflight
from judge.web.app import create_app
from judge.web.security_policy import is_local_binding


def open_browser_later(url: str) -> None:
    """browser later 모달이나 브라우저 동작을 열기 위한 상태를 준비합니다.

    Args:
        url (str): 브라우저 또는 Git 명령에 전달할 URL입니다.
    """

    def worker() -> None:
        """Uvicorn 바인딩이 시작된 뒤 브라우저를 엽니다."""
        time.sleep(0.7)
        webbrowser.open(url)

    threading.Thread(target=worker, daemon=True).start()


def run_server(
    host: str,
    port: int,
    open_browser: bool = False,
    debug: bool = False,
    allow_remote_run: bool = False,
    allow_remote_write: bool = False,
) -> None:
    """서버 실행에 필요한 입력을 준비하고 외부 프로세스나 서비스 호출을 수행합니다.

    Args:
        host (str): 서버을 계산하거나 검증할 때 필요한 host 입력입니다.
        port (int): 서버을 계산하거나 검증할 때 필요한 port 입력입니다.
        open_browser (bool): 서버 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        debug (bool): 서버 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        allow_remote_run (bool): 서버 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        allow_remote_write (bool): 비로컬 바인딩에서 관리 API를 허용할지 결정합니다.
    """
    sandbox_mode, docker = ensure_sandbox_preflight()
    if docker["sandboxReady"]:
        requirement = "required" if sandbox_mode == "docker" else "optional"
        version = f", server {docker['serverVersion']}" if docker.get("serverVersion") else ""
        print(f"Docker runtime preflight: READY ({requirement}, {docker['path']}{version}).")
    else:
        print(f"Docker runtime preflight: WARN {docker['error']}")
        print(f"Docker setup: {docker['installHint']}")
        print(
            "Docker is optional in trusted local mode; set "
            f"{SANDBOX_MODE_ENV}=docker to require this preflight."
        )
    url = f"http://{host}:{port}"
    local_binding = is_local_binding(host)
    if not local_binding:
        print(f"warning: binding to non-local host {host}; use only on trusted networks")
        if allow_remote_run:
            print("warning: remote run APIs are explicitly enabled")
        if allow_remote_write:
            print("warning: remote management APIs are explicitly enabled")
    if debug:
        os.environ["ALJ_WEB_DEBUG"] = "1"
    print(f"Local judge UI running at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        open_browser_later(url)
    uvicorn.run(
        create_app(
            local_binding=local_binding,
            remote_warning=not local_binding,
            allow_remote_run=allow_remote_run,
            allow_remote_write=allow_remote_write,
            job_history_path=default_job_history_path("judge"),
        ),
        host=host,
        port=port,
        log_level="warning",
    )
