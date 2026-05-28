from __future__ import annotations

import time
from pathlib import Path
from typing import Any, BinaryIO

from judge.core import security_limits
from judge.core.errors import JudgeError
from judge.core.paths import cache_root
from judge.core.remote import (
    download_problem_pack_from_github,
)
from judge.core.remote import (
    install_problem_pack as install_local_problem_pack,
)
from judge.utils.limited_io import copy_limited


def install_problem_pack(archive_path: str) -> dict[str, Any]:
    """Install a problem pack and return its installed path."""
    return install_local_problem_pack(Path(archive_path))


def safe_upload_name(filename: str | None, fallback: str) -> str:
    """Return a basename-only upload filename."""
    name = Path(filename or fallback).name
    if not name or name in {".", ".."}:
        raise JudgeError("invalid upload filename")
    return name


def save_upload(file_obj: BinaryIO, filename: str | None, category: str, fallback: str) -> Path:
    """Persist an uploaded file under the local judge cache."""
    name = safe_upload_name(filename, fallback)
    target_dir = cache_root() / "web-uploads" / category / str(time.time_ns())
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name
    limit = (
        security_limits.MAX_PACK_UPLOAD_BYTES
        if category == "packs"
        else security_limits.MAX_SOURCE_UPLOAD_BYTES
    )
    copy_limited(file_obj, target, limit_bytes=limit, label=f"{category} upload")
    if target.stat().st_size == 0:
        raise JudgeError("uploaded file is empty")
    return target


def save_uploaded_pack(file_obj: BinaryIO, filename: str | None) -> Path:
    """Persist an uploaded problem pack and return its path."""
    target = save_upload(file_obj, filename, "packs", "problem-pack.aljpack")
    if target.suffix != ".aljpack":
        raise JudgeError("problem pack upload must have .aljpack extension")
    return target


def install_uploaded_problem_pack(file_obj: BinaryIO, filename: str | None) -> dict[str, Any]:
    """Install an uploaded problem pack file."""
    target = save_uploaded_pack(file_obj, filename)
    result = install_problem_pack(str(target))
    result["uploadedPath"] = str(target)
    return result


def download_official_problem_pack(
    repository: str | None = None,
    asset_name: str | None = None,
    ref: str | None = None,
) -> dict[str, Any]:
    """Download and install a problem pack from the configured public GitHub repo."""
    return download_problem_pack_from_github(repository, asset_name, ref)
