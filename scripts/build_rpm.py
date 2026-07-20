"""Generate and optionally build Fedora RPM and repository-release RPM packages."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from judge import __version__
from judge.core.paths import current_platform_id

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "algorithm-local-judge"
SUPPORTED_PLATFORM = "linux-amd64"
RPM_ROOT = ROOT / "packaging" / "rpm"
RPM_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}$")
SOURCE_NAME_RE = re.compile(r"^[A-Za-z0-9._+-]+$")


def validate_rpm_platform(platform_id: str, current: str | None = None) -> None:
    """Fail before staging when the target or build host cannot produce Fedora x86_64 RPMs."""
    if platform_id != SUPPORTED_PLATFORM:
        raise ValueError(f"unsupported RPM platform: {platform_id}")
    host = current or current_platform_id()
    if host != SUPPORTED_PLATFORM:
        raise ValueError(f"RPM builds require a linux-amd64 host, current platform is {host}")


def validate_standalone_archive(archive_path: Path) -> None:
    """Require the Linux standalone root and both product launchers."""
    if not archive_path.is_file():
        raise ValueError(f"standalone archive not found: {archive_path}")
    with tarfile.open(archive_path, "r:gz") as archive:
        names = {member.name.rstrip("/") for member in archive.getmembers()}
    for launcher in ("judge", "problem-studio"):
        required = f"{PACKAGE_NAME}/bin/{launcher}"
        if required not in names:
            raise ValueError(f"standalone archive has no launcher: {required}")


def render_main_spec(version: str, source_archive: str) -> str:
    validate_rpm_version(version)
    if not SOURCE_NAME_RE.fullmatch(source_archive):
        raise ValueError(f"unsafe RPM source archive name: {source_archive}")
    return (
        (RPM_ROOT / "algorithm-local-judge.spec")
        .read_text(encoding="utf-8")
        .replace("@VERSION@", version)
        .replace("@SOURCE_ARCHIVE@", source_archive)
    )


def render_release_spec(version: str) -> str:
    validate_rpm_version(version)
    return (
        (RPM_ROOT / "alj-release.spec").read_text(encoding="utf-8").replace("@VERSION@", version)
    )


def render_repo_file(base_url: str, gpg_key_url: str) -> str:
    if (
        not base_url.startswith("https://")
        or not gpg_key_url.startswith("https://")
        or any(character.isspace() for character in base_url + gpg_key_url)
    ):
        raise ValueError("RPM repository and GPG key URLs must use HTTPS")
    return (
        (RPM_ROOT / "algorithm-local-judge.repo")
        .read_text(encoding="utf-8")
        .replace("@REPO_BASE_URL@", base_url.rstrip("/"))
        .replace("@GPG_KEY_URL@", gpg_key_url)
    )


def validate_rpm_version(version: str) -> None:
    if not RPM_VERSION_RE.fullmatch(version):
        raise ValueError(f"RPM version must be numeric: {version}")


def stage_rpmbuild_tree(
    archive_path: Path,
    topdir: Path,
    version: str,
    base_url: str,
    gpg_key_url: str,
) -> tuple[Path, Path]:
    """Stage immutable sources and rendered specs without signing or publishing."""
    validate_standalone_archive(archive_path)
    for name in ("BUILD", "BUILDROOT", "RPMS", "SOURCES", "SPECS", "SRPMS"):
        (topdir / name).mkdir(parents=True, exist_ok=True)
    source = topdir / "SOURCES" / archive_path.name
    shutil.copy2(archive_path, source)
    repo_source = topdir / "SOURCES" / "algorithm-local-judge.repo"
    repo_source.write_text(render_repo_file(base_url, gpg_key_url), encoding="utf-8")
    main_spec = topdir / "SPECS" / "algorithm-local-judge.spec"
    main_spec.write_text(render_main_spec(version, source.name), encoding="utf-8")
    release_spec = topdir / "SPECS" / "alj-release.spec"
    release_spec.write_text(render_release_spec(version), encoding="utf-8")
    return main_spec, release_spec


def build_rpms(
    archive_path: Path,
    output_dir: Path,
    version: str,
    base_url: str,
    gpg_key_url: str,
    platform_id: str = SUPPORTED_PLATFORM,
) -> list[Path]:
    validate_rpm_platform(platform_id)
    rpmbuild = shutil.which("rpmbuild")
    if rpmbuild is None:
        raise ValueError("rpmbuild is required to build Fedora packages")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="alj-rpm-build-") as tmp:
        topdir = Path(tmp) / "rpmbuild"
        specs = stage_rpmbuild_tree(archive_path.resolve(), topdir, version, base_url, gpg_key_url)
        for spec in specs:
            result = subprocess.run(
                [rpmbuild, "-bb", "--define", f"_topdir {topdir}", str(spec)],
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                raise ValueError(
                    f"rpmbuild failed for {spec.name}: {(result.stderr or result.stdout).strip()}"
                )
        built = sorted((topdir / "RPMS").rglob("*.rpm"))
        if len(built) != 2:
            raise ValueError(f"expected application and release RPMs, found {len(built)}")
        outputs = []
        for rpm in built:
            target = output_dir / rpm.name
            shutil.copy2(rpm, target)
            outputs.append(target)
        return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("dist/installers"))
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--platform", default=SUPPORTED_PLATFORM)
    parser.add_argument("--repo-base-url", required=True)
    parser.add_argument("--gpg-key-url", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        outputs = build_rpms(
            args.archive,
            args.output_dir,
            args.version,
            args.repo_base_url,
            args.gpg_key_url,
            args.platform,
        )
    except (OSError, ValueError, tarfile.TarError) as exc:
        print(f"error: {exc}")
        return 1
    for output in outputs:
        print(f"Built RPM: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
