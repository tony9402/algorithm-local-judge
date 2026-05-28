from __future__ import annotations

import stat
import zipfile
from pathlib import Path
from posixpath import normpath

from judge.core import security_limits
from judge.core.errors import JudgeError


def safe_download_name(filename: str | None, fallback: str) -> str:
    """Return a basename-only filename for a downloaded artifact."""
    name = Path(filename or fallback).name
    if not name or name in {".", ".."}:
        raise JudgeError("invalid download filename")
    return name


def safe_zip_member_path(name: str) -> Path:
    """Return a safe relative zip member path or raise."""
    normalized = normpath(name.replace("\\", "/"))
    if normalized in {"", "."}:
        raise JudgeError("unsafe empty path in source archive")
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise JudgeError(f"unsafe path in source archive: {name}")
    return path


def zip_member_mode(member: zipfile.ZipInfo) -> int:
    """Return the Unix file mode encoded in a zip member, if present."""
    return (member.external_attr >> 16) & 0o777777


def reject_unsafe_zip_member(member: zipfile.ZipInfo) -> None:
    """Reject zip members that escape extraction or represent links."""
    safe_zip_member_path(member.filename)
    mode = zip_member_mode(member)
    if mode and stat.S_ISLNK(mode):
        raise JudgeError(f"unsafe link in source archive: {member.filename}")


def safe_extract_zip(archive_path: Path, target_dir: Path) -> None:
    """Extract a zip archive after validating member paths."""
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
    """Find the package root that contains a problems directory."""
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
