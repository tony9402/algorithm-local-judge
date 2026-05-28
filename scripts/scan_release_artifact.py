from __future__ import annotations

import argparse
import glob
import tarfile
from pathlib import Path

from judge.core.checksums import verify_sha256_sidecar
from judge.core.errors import JudgeError
from judge.core.pack import FORBIDDEN_PACK_SUFFIXES, verify_pack
from judge.core.paths import current_platform_id
from judge.utils.hashing import sha256_bytes

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
    parser.add_argument(
        "--target-platform",
        action="append",
        default=[],
        help="Require an artifact for this release platform id. Can be repeated.",
    )
    parser.add_argument(
        "--require-platform-artifact",
        action="store_true",
        help="Fail when a requested target platform has no matching artifact.",
    )
    parser.add_argument(
        "--no-require-pack-checksum",
        action="store_true",
        help="Skip .aljpack sidecar checksum enforcement.",
    )
    parser.add_argument(
        "--current-platform",
        action="store_true",
        help="Require an artifact for the current platform id.",
    )
    return parser.parse_args()


def safe_member_path(name: str) -> Path:
    """Validate and return a safe archive member path."""
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise JudgeError(f"unsafe archive path: {name}")
    return path


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


def require_member(names: set[str], root_name: str, relative: str) -> None:
    """Fail when a standalone archive member is missing."""
    member_name = f"{root_name}/{relative}"
    if member_name not in names:
        raise JudgeError(f"standalone archive missing {relative}")


def validate_static_assets(names: set[str], root_name: str) -> None:
    """Validate required static assets for the packaged judge Web UI."""
    required = [
        "bin/web/static/app.js",
        "bin/web/static/styles.css",
        "bin/web/static/index.html",
    ]
    for relative in required:
        require_member(names, root_name, relative)
    module_prefix = f"{root_name}/bin/web/static/app/"
    style_prefix = f"{root_name}/bin/web/static/styles/"
    if not any(name.startswith(module_prefix) and name.endswith(".js") for name in names):
        raise JudgeError("standalone archive missing modular judge Web static assets")
    if not any(name.startswith(style_prefix) and name.endswith(".css") for name in names):
        raise JudgeError("standalone archive missing modular judge Web styles")


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
        if f"{root_name}/THIRD_PARTY_NOTICES.md" not in names:
            raise JudgeError("standalone archive missing THIRD_PARTY_NOTICES.md")
        validate_static_assets(names, root_name)
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


def artifact_platform(path: Path) -> str | None:
    """Infer a release platform id from a known artifact file name."""
    name = path.name
    for suffix in [".aljpack", ".tar.gz"]:
        if name.endswith(suffix):
            stem = name[: -len(suffix)]
            break
    else:
        return None
    parts = stem.rsplit("-", 2)
    if len(parts) < 3:
        return None
    return f"{parts[-2]}-{parts[-1]}"


def validate_platform_targets(artifacts: list[Path], target_platforms: list[str]) -> None:
    """Fail when requested release platforms are missing artifacts."""
    available = {platform for path in artifacts if (platform := artifact_platform(path))}
    missing = sorted(set(target_platforms) - available)
    if missing:
        raise JudgeError(f"missing release artifact for platform(s): {', '.join(missing)}")


def scan_artifact(path: Path, *, require_pack_checksum: bool = True) -> None:
    """Scan one release artifact based on its file name."""
    if path.suffix == ".aljpack":
        verify_pack(path)
        if require_pack_checksum:
            verify_sha256_sidecar(path)
        return
    if path.name.endswith(".tar.gz"):
        scan_standalone_archive(path)
        return
    raise JudgeError(f"unsupported release artifact: {path}")


def main() -> int:
    """CLI entry point for release artifact scanning."""
    args = parse_args()
    artifacts = [Path(path) for path in args.artifacts] if args.artifacts else default_artifacts()
    target_platforms = list(args.target_platform)
    if args.current_platform:
        target_platforms.append(current_platform_id())
    if not artifacts:
        print("No release artifacts found.")
        return 0
    try:
        if args.require_platform_artifact or target_platforms:
            validate_platform_targets(artifacts, target_platforms)
        for artifact in artifacts:
            scan_artifact(
                artifact,
                require_pack_checksum=not args.no_require_pack_checksum,
            )
            print(f"OK: {artifact}")
    except JudgeError as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
