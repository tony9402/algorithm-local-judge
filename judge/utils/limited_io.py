from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from judge.core.errors import LimitExceededError

DEFAULT_CHUNK_SIZE = 1024 * 1024


def format_limit_error(label: str, limit_bytes: int) -> str:
    """Return a user-facing size limit error."""
    return f"{label} exceeds size limit of {limit_bytes} bytes"


def ensure_bytes_limit(size: int, limit_bytes: int, label: str) -> None:
    """Raise if a byte size exceeds the configured limit."""
    if size > limit_bytes:
        raise LimitExceededError(format_limit_error(label, limit_bytes))


def ensure_text_limit(text: str, limit_bytes: int, label: str) -> bytes:
    """Return UTF-8 bytes for text after checking its byte size."""
    data = text.encode("utf-8")
    ensure_bytes_limit(len(data), limit_bytes, label)
    return data


def content_length(headers: Mapping[str, str] | object) -> int | None:
    """Return a parsed Content-Length header when available."""
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    raw = getter("Content-Length") or getter("content-length")
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None
    return value if value >= 0 else None


def ensure_content_length_limit(
    headers: Mapping[str, str] | object, limit_bytes: int, label: str
) -> None:
    """Raise when a Content-Length header is already over the configured limit."""
    length = content_length(headers)
    if length is not None:
        ensure_bytes_limit(length, limit_bytes, label)


def copy_limited(
    source: BinaryIO,
    target: Path,
    *,
    limit_bytes: int,
    label: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> int:
    """Copy a binary stream to a file while enforcing a byte limit."""
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = source.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit_bytes:
                    raise LimitExceededError(format_limit_error(label, limit_bytes))
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return written


def write_text_limited(text: str, target: Path, *, limit_bytes: int, label: str) -> int:
    """Write text after enforcing a UTF-8 byte limit."""
    data = ensure_text_limit(text, limit_bytes, label)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return len(data)


__all__ = [
    "content_length",
    "copy_limited",
    "ensure_bytes_limit",
    "ensure_content_length_limit",
    "ensure_text_limit",
    "format_limit_error",
    "write_text_limited",
]
