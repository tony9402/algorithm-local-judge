"""limited_io 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from judge.core.errors import LimitExceededError

DEFAULT_CHUNK_SIZE = 1024 * 1024


def format_limit_error(label: str, limit_bytes: int) -> str:
    """format_limit_error 함수를 실행하고 결과를 반환합니다.
    
    Args:
        label (str): `label` 값입니다.
        limit_bytes (int): `limit_bytes` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    return f"{label} exceeds size limit of {limit_bytes} bytes"


def ensure_bytes_limit(size: int, limit_bytes: int, label: str) -> None:
    """ensure_bytes_limit 함수를 실행하고 결과를 반환합니다.
    
    Args:
        size (int): `size` 값입니다.
        limit_bytes (int): `limit_bytes` 값입니다.
        label (str): `label` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    if size > limit_bytes:
        raise LimitExceededError(format_limit_error(label, limit_bytes))


def ensure_text_limit(text: str, limit_bytes: int, label: str) -> bytes:
    """ensure_text_limit 함수를 실행하고 결과를 반환합니다.
    
    Args:
        text (str): `text` 값입니다.
        limit_bytes (int): `limit_bytes` 값입니다.
        label (str): `label` 값입니다.
    
    Returns:
        bytes: 처리 결과를 반환합니다.
    """
    data = text.encode("utf-8")
    ensure_bytes_limit(len(data), limit_bytes, label)
    return data


def content_length(headers: Mapping[str, str] | object) -> int | None:
    """content_length 함수를 실행하고 결과를 반환합니다.
    
    Args:
        headers (Mapping[str, str] | object): `headers` 값입니다.
    
    Returns:
        int | None: 처리 결과를 반환합니다.
    """
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
    """ensure_content_length_limit 함수를 실행하고 결과를 반환합니다.
    
    Args:
        headers (Mapping[str, str] | object): `headers` 값입니다.
        limit_bytes (int): `limit_bytes` 값입니다.
        label (str): `label` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
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
    """copy_limited 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (BinaryIO): `source` 값입니다.
        target (Path): `target` 값입니다.
        limit_bytes (int): `limit_bytes` 값입니다.
        label (str): `label` 값입니다.
        chunk_size (int): `chunk_size` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
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
    """write_text_limited 함수를 실행하고 결과를 반환합니다.
    
    Args:
        text (str): `text` 값입니다.
        target (Path): `target` 값입니다.
        limit_bytes (int): `limit_bytes` 값입니다.
        label (str): `label` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
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
