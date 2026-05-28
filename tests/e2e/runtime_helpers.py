"""종단 간 테스트가 환경 변수와 임시 런타임 디렉터리를 격리해 사용할 수 있도록 돕는 모듈입니다."""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path


@contextlib.contextmanager
def temporary_env(values: dict[str, str]) -> Iterator[None]:
    """임시 환경 변수 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

    Args:
        values (dict[str, str]): 난수 대역이 순서대로 반환할 값 목록입니다.

    Returns:
        Iterator[None]: 호출자가 다음 검증 단계에서 사용할 결과 값입니다.
    """
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextlib.contextmanager
def isolated_runtime(prefix: str) -> Iterator[tuple[tempfile.TemporaryDirectory[str], Path]]:
    """격리 런타임 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

    Args:
        prefix (str): 접두사 값을 지정하는 인자입니다.

    Returns:
        Iterator[tuple[tempfile.TemporaryDirectory[str], Path]]: 호출자가 비교하거나 다음 명령에 전달할 문자열입니다.
    """
    directory = tempfile.TemporaryDirectory(prefix=prefix)
    try:
        yield directory, Path(directory.name)
    finally:
        directory.cleanup()
