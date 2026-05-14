from __future__ import annotations

from fastapi import HTTPException

from judge.core.errors import JudgeError


def to_http_error(exc: Exception) -> HTTPException:
    """Convert domain errors into JSON HTTP responses."""
    if isinstance(exc, JudgeError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def etag_matches(header: str | None, etag: str) -> bool:
    """Return whether an If-None-Match header contains the current ETag."""
    if not header:
        return False
    return any(item.strip() == etag or item.strip() == "*" for item in header.split(","))
