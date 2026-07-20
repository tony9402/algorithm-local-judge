"""limited io 기능을 담당하는 모듈입니다."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from judge.core.errors import LimitExceededError

DEFAULT_CHUNK_SIZE = 1024 * 1024


def format_limit_error(label: str, limit_bytes: int) -> str:
    """제한 오류 데이터를 CLI나 UI에 표시할 문자열로 변환합니다.

    Args:
        label (str): 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
        limit_bytes (int): 제한 오류을 계산하거나 검증할 때 필요한 제한 바이트 입력입니다.

    Returns:
        str: 콘솔, 로그, 또는 이벤트 스트림에 바로 쓸 수 있는 문자열입니다.
    """
    return f"{label} exceeds size limit of {limit_bytes} bytes"


def ensure_bytes_limit(size: int, limit_bytes: int, label: str) -> None:
    """바이트 제한 조건을 확인하고 위반 시 호출자가 중단할 수 있는 예외를 발생시킵니다.

    Args:
        size (int): 바이트 제한을 계산하거나 검증할 때 필요한 size 입력입니다.
        limit_bytes (int): 바이트 제한을 계산하거나 검증할 때 필요한 제한 바이트 입력입니다.
        label (str): 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
    """
    if size > limit_bytes:
        raise LimitExceededError(format_limit_error(label, limit_bytes))


def ensure_text_limit(text: str, limit_bytes: int, label: str) -> bytes:
    """텍스트 제한 조건을 확인하고 위반 시 호출자가 중단할 수 있는 예외를 발생시킵니다.

    Args:
        text (str): 화면에 표시하거나 비교에 사용할 텍스트입니다.
        limit_bytes (int): 텍스트 제한을 계산하거나 검증할 때 필요한 제한 바이트 입력입니다.
        label (str): 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
    """
    data = text.encode("utf-8")
    ensure_bytes_limit(len(data), limit_bytes, label)
    return data


def content_length(headers: Mapping[str, str] | object) -> int | None:
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
    """content length 제한 조건을 확인하고 위반 시 호출자가 중단할 수 있는 예외를 발생시킵니다.

    Args:
        headers (Mapping[str, str] | object): content length 제한을 계산하거나 검증할 때 필요한 headers 입력입니다.
        limit_bytes (int): content length 제한을 계산하거나 검증할 때 필요한 제한 바이트 입력입니다.
        label (str): 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
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
    """limited 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        source (BinaryIO): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
        target (Path): 파일을 복사하거나 산출물을 배치할 대상 경로입니다.
        limit_bytes (int): limited을 계산하거나 검증할 때 필요한 제한 바이트 입력입니다.
        label (str): 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
        chunk_size (int): limited을 계산하거나 검증할 때 필요한 chunk size 입력입니다.
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
    """텍스트 limited 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        text (str): 화면에 표시하거나 비교에 사용할 텍스트입니다.
        target (Path): 파일을 복사하거나 산출물을 배치할 대상 경로입니다.
        limit_bytes (int): 텍스트 limited을 계산하거나 검증할 때 필요한 제한 바이트 입력입니다.
        label (str): 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
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
