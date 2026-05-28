"""remote_archive 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import stat
import zipfile
from pathlib import Path
from posixpath import normpath

from judge.core import security_limits
from judge.core.errors import JudgeError


def safe_download_name(filename: str | None, fallback: str) -> str:
    """safe_download_name 함수를 실행하고 결과를 반환합니다.
    
    Args:
        filename (str | None): `filename` 값입니다.
        fallback (str): `fallback` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    name = Path(filename or fallback).name
    if not name or name in {".", ".."}:
        raise JudgeError("invalid download filename")
    return name


def safe_zip_member_path(name: str) -> Path:
    """safe_zip_member_path 함수를 실행하고 결과를 반환합니다.
    
    Args:
        name (str): 이름입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    normalized = normpath(name.replace("\\", "/"))
    if normalized in {"", "."}:
        raise JudgeError("unsafe empty path in source archive")
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise JudgeError(f"unsafe path in source archive: {name}")
    return path


def zip_member_mode(member: zipfile.ZipInfo) -> int:
    """zip_member_mode 함수를 실행하고 결과를 반환합니다.
    
    Args:
        member (zipfile.ZipInfo): `member` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
    return (member.external_attr >> 16) & 0o777777


def reject_unsafe_zip_member(member: zipfile.ZipInfo) -> None:
    """reject_unsafe_zip_member 함수를 실행하고 결과를 반환합니다.
    
    Args:
        member (zipfile.ZipInfo): `member` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    safe_zip_member_path(member.filename)
    mode = zip_member_mode(member)
    if mode and stat.S_ISLNK(mode):
        raise JudgeError(f"unsafe link in source archive: {member.filename}")


def safe_extract_zip(archive_path: Path, target_dir: Path) -> None:
    """safe_extract_zip 함수를 실행하고 결과를 반환합니다.
    
    Args:
        archive_path (Path): `archive_path` 값입니다.
        target_dir (Path): `target_dir` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > security_limits.MAX_ARCHIVE_MEMBERS:
            raise JudgeError(
                f"source archive has too many members: {len(members)} "
                f"(limit {security_limits.MAX_ARCHIVE_MEMBERS})"
            )
        total_size = 0
        for member in members:
            reject_unsafe_zip_member(member)
            if member.is_dir():
                continue
            if member.file_size > security_limits.MAX_ARCHIVE_FILE_BYTES:
                raise JudgeError(
                    f"source archive member exceeds size limit: {member.filename} "
                    f"({member.file_size} > {security_limits.MAX_ARCHIVE_FILE_BYTES})"
                )
            total_size += member.file_size
            if total_size > security_limits.MAX_ARCHIVE_TOTAL_BYTES:
                raise JudgeError(
                    "source archive extracted size exceeds limit: "
                    f"{total_size} > {security_limits.MAX_ARCHIVE_TOTAL_BYTES}"
                )
        target_dir.mkdir(parents=True, exist_ok=True)
        archive.extractall(target_dir)


def find_source_package_root(extracted_dir: Path) -> Path:
    """find_source_package_root 함수를 실행하고 결과를 반환합니다.
    
    Args:
        extracted_dir (Path): `extracted_dir` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    candidates = []
    for problems_dir in extracted_dir.rglob("problems"):
        if not problems_dir.is_dir():
            continue
        if any(
            problem_json.name == "problem.json"
            for problem_json in problems_dir.glob("*/problem.json")
        ):
            candidates.append(problems_dir.parent)
    if not candidates:
        raise JudgeError("source package archive has no problems/*/problem.json entries")
    return sorted(candidates, key=lambda path: len(path.relative_to(extracted_dir).parts))[0]
