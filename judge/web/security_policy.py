from __future__ import annotations

from fastapi import Request

from judge.core.errors import SecurityPolicyError

LOCAL_BINDING_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local_binding(host: str) -> bool:
    """Return whether a host value represents local-only binding."""
    return host in LOCAL_BINDING_HOSTS


def remote_run_allowed(request: Request) -> bool:
    """Return whether this app state allows run APIs for the current binding."""
    if bool(getattr(request.app.state, "local_binding", True)):
        return True
    return bool(getattr(request.app.state, "allow_remote_run", False))


def ensure_remote_run_allowed(request: Request) -> None:
    """Raise when run APIs are disabled for a non-local server binding."""
    if not remote_run_allowed(request):
        raise SecurityPolicyError(
            "run APIs are disabled for non-local bindings; restart with "
            "--allow-remote-run only on a trusted network"
        )


def ensure_local_web_action_allowed(request: Request, action: str) -> None:
    """Raise when a mutating web action is attempted from a non-local binding."""
    if not bool(getattr(request.app.state, "local_binding", True)):
        raise SecurityPolicyError(
            f"{action} is disabled because judge web is bound to a non-local host"
        )


def web_security_status(request: Request) -> dict[str, bool]:
    """Return JSON-safe web security policy status."""
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
