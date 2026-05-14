from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from judge import __version__
from judge.core.errors import JudgeError
from judge.core.paths import current_platform_id, executable_suffix
from judge.utils.hashing import sha256_file

ROOT = Path(__file__).resolve().parents[1]
APP_DIR_NAME = "algorithm-local-judge"


def parse_args() -> argparse.Namespace:
    """Parse standalone build script arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default=current_platform_id())
    parser.add_argument("--build-dir", default="build/nuitka")
    parser.add_argument("--stage-dir", default="build/standalone")
    parser.add_argument("--output-dir", default="dist/standalone")
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def run(command: list[str]) -> None:
    """Run one build command and fail with a readable message."""
    env = os.environ.copy()
    env.setdefault("NUITKA_CACHE_DIR", str(ROOT / "build" / "nuitka-cache"))
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, check=False)
    if result.returncode != 0:
        raise JudgeError(f"command failed with exit code {result.returncode}: {' '.join(command)}")


def find_nuitka_dist(build_dir: Path) -> Path:
    """Find the standalone distribution directory produced by Nuitka."""
    candidates = sorted(
        [path for path in build_dir.rglob("*.dist") if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise JudgeError(f"Nuitka distribution directory not found under {build_dir}")
    return candidates[0]


def write_checksums(app_root: Path) -> None:
    """Write SHA-256 checksums for all regular files in the staged app."""
    entries = []
    for path in sorted(item for item in app_root.rglob("*") if item.is_file()):
        if path.name == "checksums.txt":
            continue
        entries.append(f"{sha256_file(path)}  {path.relative_to(app_root).as_posix()}")
    (app_root / "checksums.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")


def copy_optional_docs(app_root: Path) -> None:
    """Copy user-facing documents into the standalone app root when present."""
    for name in ["README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"]:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, app_root / name)


def create_archive(app_root: Path, output_dir: Path, platform_id: str) -> Path:
    """Create the final tar.gz standalone archive."""
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{APP_DIR_NAME}-{__version__}-{platform_id}.tar.gz"
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(app_root, arcname=APP_DIR_NAME)
    return archive_path


def build_standalone(args: argparse.Namespace) -> Path:
    """Build a Nuitka standalone app and return the archive path."""
    current_platform = current_platform_id()
    if args.platform != current_platform:
        raise JudgeError(
            "cross-platform standalone build is not implemented yet; "
            f"current platform is {current_platform}, requested {args.platform}"
        )

    build_dir = (ROOT / args.build_dir).resolve()
    stage_root = (ROOT / args.stage_dir / args.platform).resolve()
    output_dir = (ROOT / args.output_dir).resolve()
    if args.clean:
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(stage_root, ignore_errors=True)

    build_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=standalone",
        "--python-flag=no_docstrings",
        "--python-flag=no_asserts",
        "--include-module=yaml",
        "--include-data-dir=judge/web/static=web/static",
        "--output-filename=judge",
        f"--output-dir={build_dir}",
        "judge/__main__.py",
    ]
    run(command)

    dist_dir = find_nuitka_dist(build_dir)
    app_root = stage_root / APP_DIR_NAME
    bin_dir = app_root / "bin"
    shutil.rmtree(app_root, ignore_errors=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    for item in dist_dir.iterdir():
        target = bin_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    expected_executable = bin_dir / f"judge{executable_suffix()}"
    if not expected_executable.exists():
        bin_executable = bin_dir / "judge.bin"
        if bin_executable.exists():
            bin_executable.rename(expected_executable)
    if not expected_executable.exists():
        raise JudgeError(f"standalone executable not found: {expected_executable}")
    expected_executable.chmod(expected_executable.stat().st_mode | 0o755)

    copy_optional_docs(app_root)
    write_checksums(app_root)
    return create_archive(app_root, output_dir, args.platform)


def main() -> int:
    """CLI entry point for local standalone builds."""
    try:
        archive_path = build_standalone(parse_args())
    except JudgeError as exc:
        print(f"error: {exc}")
        return 1
    print(f"Built standalone archive: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
