from __future__ import annotations

import argparse
import glob
import hashlib
import tarfile
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.pack import FORBIDDEN_PACK_SUFFIXES, verify_pack

FORBIDDEN_STANDALONE_SUFFIXES = {
    *FORBIDDEN_PACK_SUFFIXES,
    ".py",
    ".pdb",
}
FORBIDDEN_STANDALONE_NAMES = {".dsym", "__pycache__"}


def parse_args() -> argparse.Namespace:
    """Parse release artifact scanner arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", nargs="*")
    return parser.parse_args()


def safe_member_path(name: str) -> Path:
    """Validate and return a safe archive member path."""
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise JudgeError(f"unsafe archive path: {name}")
    return path


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest for archive member bytes."""
    return hashlib.sha256(data).hexdigest()


def read_member_bytes(archive: tarfile.TarFile, member_name: str) -> bytes:
    """Read one regular file from a tar archive."""
    member = archive.getmember(member_name)
    file = archive.extractfile(member)
    if file is None:
        raise JudgeError(f"cannot read archive member: {member_name}")
    return file.read()


def validate_checksums(archive: tarfile.TarFile, root_name: str) -> None:
    """Validate checksums.txt inside a standalone archive."""
    checksums_name = f"{root_name}/checksums.txt"
    names = {member.name for member in archive.getmembers()}
    if checksums_name not in names:
        raise JudgeError("standalone archive missing checksums.txt")
    lines = read_member_bytes(archive, checksums_name).decode("utf-8").splitlines()
    for line in lines:
        if not line.strip():
            continue
        expected_hash, relative = line.split(maxsplit=1)
        member_name = f"{root_name}/{relative}"
        if member_name not in names:
            raise JudgeError(f"checksum target missing: {relative}")
        actual_hash = sha256_bytes(read_member_bytes(archive, member_name))
        if actual_hash != expected_hash:
            raise JudgeError(f"checksum mismatch: {relative}")


def scan_standalone_archive(archive_path: Path) -> None:
    """Scan a standalone tar.gz artifact for release policy violations."""
    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
        if not members:
            raise JudgeError(f"empty standalone archive: {archive_path}")
        root_name = safe_member_path(members[0].name).parts[0]
        names = {member.name for member in members}
        executable_candidates = {
            f"{root_name}/bin/judge",
            f"{root_name}/bin/judge.exe",
        }
        if not names.intersection(executable_candidates):
            raise JudgeError("standalone archive missing bin/judge executable")
        if f"{root_name}/README.md" not in names:
            raise JudgeError("standalone archive missing README.md")
        for member in members:
            path = safe_member_path(member.name)
            lowered_name = path.name.lower()
            if member.isdir() and lowered_name in FORBIDDEN_STANDALONE_NAMES:
                raise JudgeError(f"forbidden directory in standalone archive: {member.name}")
            if member.isfile() and path.suffix.lower() in FORBIDDEN_STANDALONE_SUFFIXES:
                raise JudgeError(f"forbidden file in standalone archive: {member.name}")
        validate_checksums(archive, root_name)


def default_artifacts() -> list[Path]:
    """Return release artifacts discovered in the default dist directories."""
    patterns = ["dist/standalone/*.tar.gz", "dist/packs/*.aljpack"]
    paths = []
    for pattern in patterns:
        paths.extend(Path(path) for path in glob.glob(pattern))
    return sorted(paths)


def scan_artifact(path: Path) -> None:
    """Scan one release artifact based on its file name."""
    if path.suffix == ".aljpack":
        verify_pack(path)
        return
    if path.name.endswith(".tar.gz"):
        scan_standalone_archive(path)
        return
    raise JudgeError(f"unsupported release artifact: {path}")


def main() -> int:
    """CLI entry point for release artifact scanning."""
    args = parse_args()
    artifacts = [Path(path) for path in args.artifacts] if args.artifacts else default_artifacts()
    if not artifacts:
        print("No release artifacts found.")
        return 0
    try:
        for artifact in artifacts:
            scan_artifact(artifact)
            print(f"OK: {artifact}")
    except JudgeError as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
