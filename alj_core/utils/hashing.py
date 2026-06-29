"""hashing 기능을 담당하는 모듈입니다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """sha256 파일 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 sha256 파일 문자열입니다.
    """
    return sha256_bytes(path.read_bytes())


def sha256_json(data: Any) -> str:
    return sha256_bytes(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8"))
