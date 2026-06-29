"""보안 정책 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
"""
from __future__ import annotations

from fastapi import Request

from alj_core.errors import SecurityPolicyError

LOCAL_BINDING_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local_binding(host: str) -> bool:
    """로컬 binding 여부를 실제 파일, 설정, 또는 런타임 상태를 기준으로 판정합니다.

    Args:
        host (str): 로컬 binding을 계산하거나 검증할 때 필요한 host 입력입니다.

    Returns:
        bool: 로컬 binding 조건을 만족하면 True, 아니면 False입니다.
    """
    return host in LOCAL_BINDING_HOSTS


def workspace_write_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state, "workspace_write_enabled", True))


def ensure_local_write_allowed(request: Request, action: str) -> None:
    """현재 요청에서 로컬 파일 변경이 허용되는지 확인하고 차단된 작업이면 HTTP 오류를 발생시킵니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        action (str): 로컬 쓰기 allowed을 계산하거나 검증할 때 필요한 action 입력입니다.
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
