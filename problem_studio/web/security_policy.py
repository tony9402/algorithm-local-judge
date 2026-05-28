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


def workspace_write_enabled(request: Request) -> bool:
    """workspace_write_enabled 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    return bool(getattr(request.app.state, "workspace_write_enabled", True))


def ensure_local_write_allowed(request: Request, action: str) -> None:
    """ensure_local_write_allowed 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        action (str): `action` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    if not workspace_write_enabled(request):
        raise SecurityPolicyError(
            f"{action} is disabled because Problem Studio is bound to a non-local host"
        )


__all__ = [
    "LOCAL_BINDING_HOSTS",
    "ensure_local_write_allowed",
    "is_local_binding",
    "workspace_write_enabled",
]
