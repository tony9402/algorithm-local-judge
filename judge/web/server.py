"""server 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import os
import threading
import time
import webbrowser

import uvicorn

from judge.web.app import create_app
from judge.web.security_policy import is_local_binding


def open_browser_later(url: str) -> None:
    """open_browser_later 함수를 실행하고 결과를 반환합니다.
    
    Args:
        url (str): `url` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    def worker() -> None:
        """worker 함수를 실행하고 결과를 반환합니다.
        
        Args:
            없음
        
        Returns:
            None: 처리 결과를 반환합니다.
        """
        time.sleep(0.7)
        webbrowser.open(url)

    threading.Thread(target=worker, daemon=True).start()


def run_server(
    host: str,
    port: int,
    open_browser: bool = False,
    debug: bool = False,
    allow_remote_run: bool = False,
) -> None:
    """run_server 함수를 실행하고 결과를 반환합니다.
    
    Args:
        host (str): `host` 값입니다.
        port (int): `port` 값입니다.
        open_browser (bool): `open_browser` 값입니다.
        debug (bool): `debug` 값입니다.
        allow_remote_run (bool): `allow_remote_run` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    url = f"http://{host}:{port}"
    local_binding = is_local_binding(host)
    if not local_binding:
        print(f"warning: binding to non-local host {host}; use only on trusted networks")
        if allow_remote_run:
            print("warning: remote run APIs are explicitly enabled")
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
        ),
        host=host,
        port=port,
        log_level="warning",
    )
