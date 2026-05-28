from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path


@contextlib.contextmanager
def temporary_env(values: dict[str, str]) -> Iterator[None]:
    """Temporarily set environment variables for an E2E server."""
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
    directory = tempfile.TemporaryDirectory(prefix=prefix)
    try:
        yield directory, Path(directory.name)
    finally:
        directory.cleanup()
