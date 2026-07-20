"""릴리스 산출물의 플랫폼 누락, 패키지 체크섬, standalone 아카이브 구성과 금지 파일 포함 여부를 검증하는 스크립트입니다."""

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
    """릴리스 산출물 경로와 플랫폼 필수 여부, 패키지 체크섬 검사 옵션을 파싱합니다.

    Returns:
        argparse.Namespace: 릴리스 스캐너 실행 옵션을 담은 명령줄 인자 네임스페이스입니다.
    """
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
    """아카이브 멤버명이 절대 경로나 상위 디렉터리 참조를 포함하지 않는지 검증합니다.

    Args:
        name (str): tar 아카이브에서 읽은 멤버 이름입니다.

    Returns:
        Path: 안전성이 확인된 상대 멤버 경로입니다.
    """
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise JudgeError(f"unsafe archive path: {name}")
    return path


def read_member_bytes(archive: tarfile.TarFile, member_name: str) -> bytes:
    """tar 아카이브에서 지정한 일반 파일 멤버를 읽어 바이트열로 반환합니다.

    Args:
        archive (tarfile.TarFile): 검사 중인 standalone tar 아카이브입니다.
        member_name (str): 읽을 파일 멤버 이름입니다.

    Returns:
        bytes: 아카이브 멤버의 전체 바이트 내용입니다.
    """
    member = archive.getmember(member_name)
    file = archive.extractfile(member)
    if file is None:
        raise JudgeError(f"cannot read archive member: {member_name}")
    return file.read()


def validate_checksums(archive: tarfile.TarFile, root_name: str) -> None:
    """standalone 아카이브 안의 checksums.txt를 기준으로 포함 파일의 해시가 일치하는지 검증합니다.

    Args:
        archive (tarfile.TarFile): 검사 중인 standalone tar 아카이브입니다.
        root_name (str): 아카이브 내부 앱 루트 디렉터리 이름입니다.
    """
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
    """standalone 아카이브에 필수 상대 경로가 포함되어 있는지 확인합니다.

    Args:
        names (set[str]): 아카이브에 포함된 전체 멤버 이름 집합입니다.
        root_name (str): 아카이브 내부 앱 루트 디렉터리 이름입니다.
        relative (str): 앱 루트 기준으로 반드시 존재해야 하는 상대 경로입니다.
    """
    member_name = f"{root_name}/{relative}"
    if member_name not in names:
        raise JudgeError(f"standalone archive missing {relative}")


def validate_static_assets(names: set[str], root_name: str) -> None:
    """패키징된 두 웹 UI가 실행에 필요한 정적 자산을 포함하는지 검증합니다.

    Args:
        names (set[str]): 아카이브에 포함된 전체 멤버 이름 집합입니다.
        root_name (str): 아카이브 내부 앱 루트 디렉터리 이름입니다.
    """
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

    studio_required = [
        "bin/studio-web/static/app.js",
        "bin/studio-web/static/styles.css",
        "bin/studio-web/static/index.html",
        "bin/studio-web/static/fragments/workspace.html",
        "bin/studio-web/static/vendor/codemirror/codemirror.min.css",
        "bin/studio-web/static/vendor/codemirror/codemirror.min.js",
    ]
    for relative in studio_required:
        require_member(names, root_name, relative)
    studio_module_prefix = f"{root_name}/bin/studio-web/static/app/"
    studio_style_prefix = f"{root_name}/bin/studio-web/static/styles/"
    if not any(name.startswith(studio_module_prefix) and name.endswith(".js") for name in names):
        raise JudgeError("standalone archive missing modular Problem Studio static assets")
    if not any(name.startswith(studio_style_prefix) and name.endswith(".css") for name in names):
        raise JudgeError("standalone archive missing modular Problem Studio styles")


def scan_standalone_archive(archive_path: Path) -> None:
    """standalone tar.gz 산출물이 실행 파일, 문서, 정적 자산, 금지 확장자, 체크섬 정책을 모두 만족하는지 검사합니다.

    Args:
        archive_path (Path): 검사할 standalone tar.gz 파일 경로입니다.
    """
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
        studio_executable_candidates = {
            f"{root_name}/bin/problem-studio",
            f"{root_name}/bin/problem-studio.exe",
        }
        if not names.intersection(studio_executable_candidates):
            raise JudgeError("standalone archive missing bin/problem-studio executable")
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
    """기본 dist 디렉터리에서 standalone 아카이브와 .aljpack 패키지를 찾습니다.

    Returns:
        list[Path]: 파일명 순으로 정렬된 기본 릴리스 산출물 경로 목록입니다.
    """
    patterns = ["dist/standalone/*.tar.gz", "dist/packs/*.aljpack"]
    paths = []
    for pattern in patterns:
        paths.extend(Path(path) for path in glob.glob(pattern))
    return sorted(paths)


def artifact_platform(path: Path) -> str | None:
    """릴리스 산출물 파일명에서 플랫폼 식별자를 추론합니다.

    Args:
        path (Path): 플랫폼 식별자를 읽을 릴리스 산출물 경로입니다.

    Returns:
        str | None: 파일명에서 추론한 플랫폼 식별자입니다. 형식이 맞지 않으면 `None`입니다.
    """
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
    """요청된 릴리스 플랫폼마다 대응하는 산출물이 존재하는지 확인합니다.

    Args:
        artifacts (list[Path]): 검사 대상 릴리스 산출물 경로 목록입니다.
        target_platforms (list[str]): 반드시 존재해야 하는 플랫폼 식별자 목록입니다.
    """
    available = {platform for path in artifacts if (platform := artifact_platform(path))}
    missing = sorted(set(target_platforms) - available)
    if missing:
        raise JudgeError(f"missing release artifact for platform(s): {', '.join(missing)}")


def scan_artifact(path: Path, *, require_pack_checksum: bool = True) -> None:
    """파일 확장자에 따라 .aljpack 또는 standalone tar.gz 산출물 검사를 수행합니다.

    Args:
        path (Path): 검사할 릴리스 산출물 경로입니다.
        require_pack_checksum (bool): .aljpack 산출물에 동반 SHA-256 체크섬 파일을 요구할지 여부입니다.
    """
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
    """릴리스 산출물을 찾고 플랫폼 요구사항과 파일별 정책 검사를 실행합니다.

    Returns:
        int: 모든 검사가 통과하면 0, 릴리스 정책 오류가 있으면 1입니다.
    """
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
