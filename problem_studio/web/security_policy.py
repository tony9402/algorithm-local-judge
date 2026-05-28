from __future__ import annotations

from fastapi import Request

from judge.core.errors import SecurityPolicyError

LOCAL_BINDING_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local_binding(host: str) -> bool:
    """Return whether a host value represents local-only binding."""
    return host in LOCAL_BINDING_HOSTS


def workspace_write_enabled(request: Request) -> bool:
    """Return whether workspace/file mutation APIs are enabled."""
    return bool(getattr(request.app.state, "workspace_write_enabled", True))


def ensure_local_write_allowed(request: Request, action: str) -> None:
    """Raise when write APIs are disabled for a non-local server binding."""
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
