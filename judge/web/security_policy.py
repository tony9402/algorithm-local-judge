"""security_policy 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import Request

from judge.core.errors import SecurityPolicyError

LOCAL_BINDING_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local_binding(host: str) -> bool:
    """is_local_binding 함수를 실행하고 결과를 반환합니다.
    
    Args:
        host (str): `host` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    return host in LOCAL_BINDING_HOSTS


def remote_run_allowed(request: Request) -> bool:
    """remote_run_allowed 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    if bool(getattr(request.app.state, "local_binding", True)):
        return True
    return bool(getattr(request.app.state, "allow_remote_run", False))


def ensure_remote_run_allowed(request: Request) -> None:
    """ensure_remote_run_allowed 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    if not remote_run_allowed(request):
        raise SecurityPolicyError(
            "run APIs are disabled for non-local bindings; restart with "
            "--allow-remote-run only on a trusted network"
        )


def ensure_local_web_action_allowed(request: Request, action: str) -> None:
    """ensure_local_web_action_allowed 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        action (str): `action` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    if not bool(getattr(request.app.state, "local_binding", True)):
        raise SecurityPolicyError(
            f"{action} is disabled because judge web is bound to a non-local host"
        )


def web_security_status(request: Request) -> dict[str, bool]:
    """web_security_status 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict[str, bool]: 처리 결과를 반환합니다.
    """
    return {
        "localBinding": bool(getattr(request.app.state, "local_binding", True)),
        "remoteWarning": bool(getattr(request.app.state, "remote_warning", False)),
        "remoteRunAllowed": remote_run_allowed(request),
    }


__all__ = [
    "LOCAL_BINDING_HOSTS",
    "ensure_remote_run_allowed",
    "ensure_local_web_action_allowed",
    "is_local_binding",
    "remote_run_allowed",
    "web_security_status",
]
