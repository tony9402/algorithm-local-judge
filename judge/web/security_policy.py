"""보안 정책 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
"""
from __future__ import annotations

from fastapi import Request

from judge.core.errors import SecurityPolicyError

LOCAL_BINDING_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local_binding(host: str) -> bool:
    """로컬 binding 여부를 실제 파일, 설정, 또는 런타임 상태를 기준으로 판정합니다.

    Args:
        host (str): 로컬 binding을 계산하거나 검증할 때 필요한 host 입력입니다.

    Returns:
        bool: 로컬 binding 조건을 만족하면 True, 아니면 False입니다.
    """
    return host in LOCAL_BINDING_HOSTS


def remote_run_allowed(request: Request) -> bool:
    if bool(getattr(request.app.state, "local_binding", True)):
        return True
    return bool(getattr(request.app.state, "allow_remote_run", False))


def ensure_remote_run_allowed(request: Request) -> None:
    """웹 요청이 제출 코드 실행을 허용하는 보안 정책을 만족하는지 확인합니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
    """
    if not remote_run_allowed(request):
        raise SecurityPolicyError(
            "run APIs are disabled for non-local bindings; restart with "
            "--allow-remote-run only on a trusted network"
        )


def ensure_local_web_action_allowed(request: Request, action: str) -> None:
    """로컬 웹 action allowed 조건을 확인하고 위반 시 호출자가 중단할 수 있는 예외를 발생시킵니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        action (str): 로컬 웹 action allowed을 계산하거나 검증할 때 필요한 action 입력입니다.
    """
    if not bool(getattr(request.app.state, "local_binding", True)):
        raise SecurityPolicyError(
            f"{action} is disabled because judge web is bound to a non-local host"
        )


def web_security_status(request: Request) -> dict[str, bool]:
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
