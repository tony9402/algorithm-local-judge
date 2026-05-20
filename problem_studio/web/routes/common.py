from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from fastapi import HTTPException, Request

from judge.core.errors import JudgeError
from problem_studio.web.jobs import BackgroundJobStore
from problem_studio.web.streaming import sse, stream_operation

T = TypeVar("T")


def workspace_from_request(request: Request) -> Path:
    """Return the active problem-studio workspace from app state."""
    return request.app.state.workspace


def jobs_from_request(request: Request) -> BackgroundJobStore:
    """Return the in-memory background job store for the local web session."""
    return request.app.state.jobs


def to_http_error(exc: Exception) -> HTTPException:
    """Convert domain errors into JSON HTTP responses."""
    if isinstance(exc, JudgeError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def route_result(operation: Callable[[], T]) -> T:
    """Run a route operation and convert domain exceptions into HTTP errors."""
    try:
        return operation()
    except Exception as exc:
        raise to_http_error(exc) from exc


__all__ = [
    "jobs_from_request",
    "route_result",
    "sse",
    "stream_operation",
    "to_http_error",
    "workspace_from_request",
]
