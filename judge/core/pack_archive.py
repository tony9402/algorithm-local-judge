from __future__ import annotations

import tarfile
from pathlib import Path

from judge.core import security_limits
from judge.core.errors import JudgeError

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
    """Reject source or debug artifacts that must not be released in packs."""
    lowered_name = path.name.lower()
    if path.suffix.lower() in FORBIDDEN_PACK_SUFFIXES or lowered_name in FORBIDDEN_PACK_NAMES:
        raise JudgeError(f"forbidden file in problem pack: {path}")


def safe_tar_members(archive_path: Path) -> list[tarfile.TarInfo]:
    """Return tar members after checking archive paths and unsafe entry types."""
    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
    if len(members) > security_limits.MAX_ARCHIVE_MEMBERS:
        raise JudgeError(
            f"pack archive has too many members: {len(members)} "
            f"(limit {security_limits.MAX_ARCHIVE_MEMBERS})"
        )
    total_size = 0
    for member in members:
        member_path = Path(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise JudgeError(f"unsafe path in pack archive: {member.name}")
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
    return members


def safe_extract_tar(archive_path: Path, target_dir: Path) -> None:
    """Extract a tar archive after validating member paths."""
    members = safe_tar_members(archive_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:*") as archive:
        try:
            archive.extractall(target_dir, members=members, filter="data")
        except TypeError:
            archive.extractall(target_dir, members=members)


def single_pack_dir(extracted_dir: Path) -> Path:
    """Return the single top-level pack directory from an extracted archive."""
    candidates = [path for path in extracted_dir.iterdir() if path.is_dir()]
    if len(candidates) != 1:
        raise JudgeError("pack archive must contain exactly one top-level directory")
    return candidates[0]
