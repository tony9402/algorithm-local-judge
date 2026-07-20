"""문제팩 아카이브 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

import os
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath

from alj_core import security_limits
from alj_core.errors import JudgeError

FORBIDDEN_PACK_SUFFIXES = {
    ".cpp",
    ".cc",
    ".cxx",
    ".hpp",
    ".hh",
    ".hxx",
    ".h",
    ".pdb",
    ".o",
    ".obj",
    ".a",
    ".lib",
}
FORBIDDEN_PACK_NAMES = {".dsym"}
PACK_SCHEMA_VERSION = 1


def reject_forbidden_release_file(path: Path) -> None:
    lowered_name = path.name.lower()
    if path.suffix.lower() in FORBIDDEN_PACK_SUFFIXES or lowered_name in FORBIDDEN_PACK_NAMES:
        raise JudgeError(f"forbidden file in problem pack: {path}")


def safe_tar_members(archive_path: Path) -> list[tarfile.TarInfo]:
    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
    if len(members) > security_limits.MAX_ARCHIVE_MEMBERS:
        raise JudgeError(
            f"pack archive has too many members: {len(members)} "
            f"(limit {security_limits.MAX_ARCHIVE_MEMBERS})"
        )
    total_size = 0
    seen_paths: dict[str, tarfile.TarInfo] = {}
    validated_members: list[tarfile.TarInfo] = []
    for member in members:
        normalized_name = member.name.replace("\\", "/")
        member_path = PurePosixPath(normalized_name)
        if (
            not normalized_name
            or normalized_name.startswith("/")
            or re.match(r"^[A-Za-z]:($|/)", normalized_name)
            or member_path.is_absolute()
            or ".." in member_path.parts
        ):
            raise JudgeError(f"unsafe path in pack archive: {member.name}")
        normalized = member_path.as_posix()
        if member.issym() or member.islnk():
            raise JudgeError(f"unsafe link in pack archive: {member.name}")
        if not (member.isfile() or member.isdir()):
            raise JudgeError(f"unsupported member type in pack archive: {member.name}")
        if member.isfile():
            if member.size > security_limits.MAX_ARCHIVE_FILE_BYTES:
                raise JudgeError(
                    f"pack archive member exceeds size limit: {member.name} "
                    f"({member.size} > {security_limits.MAX_ARCHIVE_FILE_BYTES})"
                )
            total_size += member.size
            if total_size > security_limits.MAX_ARCHIVE_TOTAL_BYTES:
                raise JudgeError(
                    "pack archive extracted size exceeds limit: "
                    f"{total_size} > {security_limits.MAX_ARCHIVE_TOTAL_BYTES}"
                )
        previous = seen_paths.get(normalized)
        if previous is not None:
            if member.isdir() and previous.isdir():
                continue
            if (
                member.isfile()
                and previous.isfile()
                and member.size == previous.size
                and _same_tar_file(archive_path, previous, member)
            ):
                continue
            raise JudgeError(f"duplicate path in pack archive: {member.name}")
        seen_paths[normalized] = member
        validated_members.append(member)
    return validated_members


def _same_tar_file(
    archive_path: Path,
    first: tarfile.TarInfo,
    second: tarfile.TarInfo,
) -> bool:
    """Return whether duplicate regular-file entries contain identical bytes."""
    with tarfile.open(archive_path, "r:*") as archive:
        first_stream = archive.extractfile(first)
        second_stream = archive.extractfile(second)
        if first_stream is None or second_stream is None:
            return False
        with first_stream, second_stream:
            while True:
                first_chunk = first_stream.read(1024 * 1024)
                second_chunk = second_stream.read(1024 * 1024)
                if first_chunk != second_chunk:
                    return False
                if not first_chunk:
                    return True


def safe_extract_tar(archive_path: Path, target_dir: Path) -> None:
    """안전 extract tar 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        archive_path (Path): 아카이브 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        target_dir (Path): target dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
    """
    members = safe_tar_members(archive_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:*") as archive:
        for member in members:
            relative = PurePosixPath(member.name.replace("\\", "/"))
            destination = target_dir.joinpath(*relative.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise JudgeError(f"could not read pack archive member: {member.name}")
            with source, destination.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            try:
                os.chmod(destination, member.mode & 0o7777)
            except OSError:
                pass


def single_pack_dir(extracted_dir: Path) -> Path:
    candidates = [path for path in extracted_dir.iterdir() if path.is_dir()]
    if len(candidates) != 1:
        raise JudgeError("pack archive must contain exactly one top-level directory")
    return candidates[0]
