"""hashing 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    """sha256_bytes 함수를 실행하고 결과를 반환합니다.
    
    Args:
        data (bytes): 처리할 데이터입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """sha256_file 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    return sha256_bytes(path.read_bytes())


def sha256_json(data: Any) -> str:
    """sha256_json 함수를 실행하고 결과를 반환합니다.
    
    Args:
        data (Any): 처리할 데이터입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    return sha256_bytes(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8"))
