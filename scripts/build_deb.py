"""Build a Debian package from the already verified Linux standalone archive."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from alj_core.errors import JudgeError
from alj_core.pack_archive import safe_extract_tar
from judge import __version__

PACKAGE_NAME = "algorithm-local-judge"


def control_text(version: str) -> str:
    return f"""Package: {PACKAGE_NAME}
Version: {version}
Section: devel
Priority: optional
Architecture: amd64
Maintainer: Algorithm Local Judge maintainers
Depends: ca-certificates
Recommends: docker.io, build-essential, openjdk-17-jdk-headless, python3, pypy3
Description: Local web judge and problem authoring studio
 Judge and Problem Studio run on the user's computer and open their web interfaces on loopback.
 Docker is recommended for an isolated local execution environment.
"""


def stage_deb(standalone_archive: Path, stage: Path, version: str) -> None:
    extraction = stage.parent / "standalone"
    extraction.mkdir(parents=True, exist_ok=True)
    safe_extract_tar(standalone_archive, extraction)
    standalone = extraction / PACKAGE_NAME
    executables = {name: standalone / "bin" / name for name in ("judge", "problem-studio")}
    for executable in executables.values():
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError(f"standalone archive has no executable: {executable}")

    application = stage / "opt" / PACKAGE_NAME
    application.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(standalone, application)
    binary_dir = stage / "usr" / "bin"
    binary_dir.mkdir(parents=True, exist_ok=True)
    for name in executables:
        (binary_dir / name).symlink_to(f"/opt/{PACKAGE_NAME}/bin/{name}")
    control = stage / "DEBIAN" / "control"
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text(control_text(version), encoding="utf-8")


def build_deb(standalone_archive: Path, output_dir: Path, version: str) -> Path:
    if shutil.which("dpkg-deb") is None:
        raise ValueError("dpkg-deb is required to build the Linux installer")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{PACKAGE_NAME}_{version}_amd64.deb"
    with tempfile.TemporaryDirectory(prefix="alj-deb-build-") as tmp:
        stage = Path(tmp) / f"{PACKAGE_NAME}_{version}_amd64"
        stage_deb(standalone_archive.resolve(), stage, version)
        result = subprocess.run(
            ["dpkg-deb", "--root-owner-group", "--build", str(stage), str(output)],
            text=True,
            capture_output=True,
            check=False,
        )
    if result.returncode != 0:
        raise ValueError(f"dpkg-deb failed: {(result.stderr or result.stdout).strip()}")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("dist/installers"))
    parser.add_argument("--version", default=__version__)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = build_deb(args.archive, args.output_dir, args.version)
    except (OSError, ValueError, JudgeError) as exc:
        print(f"error: {exc}")
        return 1
    print(f"Built Debian installer: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
