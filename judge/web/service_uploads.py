"""서비스 uploads 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
"""
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
    return install_local_problem_pack(Path(archive_path))


def safe_upload_name(filename: str | None, fallback: str) -> str:
    name = Path(filename or fallback).name
    if not name or name in {".", ".."}:
        raise JudgeError("invalid upload filename")
    return name


def save_upload(file_obj: BinaryIO, filename: str | None, category: str, fallback: str) -> Path:
    """업로드 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        file_obj (BinaryIO): 업로드을 계산하거나 검증할 때 필요한 파일 obj 입력입니다.
        filename (str | None): 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.
        category (str): 업로드을 계산하거나 검증할 때 필요한 category 입력입니다.
        fallback (str): 업로드을 계산하거나 검증할 때 필요한 fallback 입력입니다.

    Returns:
        Path: 검증된 업로드 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
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
    """uploaded 문제팩 데이터를 다음 요청에서도 사용할 수 있도록 안전한 위치에 저장합니다.

    Args:
        file_obj (BinaryIO): uploaded 문제팩을 계산하거나 검증할 때 필요한 파일 obj 입력입니다.
        filename (str | None): 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.

    Returns:
        Path: 검증된 uploaded 문제팩 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    target = save_upload(file_obj, filename, "packs", "problem-pack.aljpack")
    if target.suffix != ".aljpack":
        raise JudgeError("problem pack upload must have .aljpack extension")
    return target


def install_uploaded_problem_pack(file_obj: BinaryIO, filename: str | None) -> dict[str, Any]:
    target = save_uploaded_pack(file_obj, filename)
    result = install_problem_pack(str(target))
    result["uploadedPath"] = str(target)
    return result


def download_official_problem_pack(
    repository: str | None = None,
    asset_name: str | None = None,
    ref: str | None = None,
) -> dict[str, Any]:
    return download_problem_pack_from_github(repository, asset_name, ref)
