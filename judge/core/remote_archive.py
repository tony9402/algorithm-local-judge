"""원격 아카이브 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from posixpath import normpath

from judge.core import security_limits
from judge.core.errors import JudgeError


def safe_download_name(filename: str | None, fallback: str) -> str:
    name = Path(filename or fallback).name
    if not name or name in {".", ".."}:
        raise JudgeError("invalid download filename")
    return name


def safe_zip_member_path(name: str) -> Path:
    normalized = normpath(name.replace("\\", "/"))
    if normalized in {"", "."}:
        raise JudgeError("unsafe empty path in source archive")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or normalized.startswith("/")
        or (len(normalized) >= 2 and normalized[1] == ":")
        or ".." in path.parts
    ):
        raise JudgeError(f"unsafe path in source archive: {name}")
    return Path(*path.parts)


def zip_member_mode(member: zipfile.ZipInfo) -> int:
    return (member.external_attr >> 16) & 0o777777


def reject_unsafe_zip_member(member: zipfile.ZipInfo) -> None:
    safe_zip_member_path(member.filename)
    mode = zip_member_mode(member)
    if mode and stat.S_ISLNK(mode):
        raise JudgeError(f"unsafe link in source archive: {member.filename}")


def safe_extract_zip(archive_path: Path, target_dir: Path) -> None:
    """안전 extract zip 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        archive_path (Path): 아카이브 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        target_dir (Path): target dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
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
        seen_paths: set[Path] = set()
        for member in members:
            relative = safe_zip_member_path(member.filename)
            if relative in seen_paths:
                raise JudgeError(f"duplicate path in source archive: {member.filename}")
            seen_paths.add(relative)
            destination = target_dir.joinpath(*relative.parts)
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            mode = zip_member_mode(member) & 0o7777
            if mode:
                try:
                    os.chmod(destination, mode)
                except OSError:
                    pass


def find_source_package_root(extracted_dir: Path) -> Path:
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
