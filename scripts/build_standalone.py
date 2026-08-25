"""Nuitka로 judge 독립 실행 배포판을 만들고 문서, 체크섬, 압축 아카이브를 구성하는 릴리스 빌드 스크립트입니다."""

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
JUDGE_STATIC_DESTINATION = "web/static"
STUDIO_STATIC_DESTINATION = "studio-web/static"
SUPPORTED_PLATFORMS = {
    "linux-amd64",
    "macos-amd64",
    "macos-arm64",
    "windows-amd64",
}


def parse_args() -> argparse.Namespace:
    """독립 실행 배포판 빌드에 필요한 플랫폼, 빌드 디렉터리, 스테이징 디렉터리, 출력 디렉터리, 정리 옵션을 파싱합니다.

    Returns:
        argparse.Namespace: standalone 빌드 옵션을 담은 명령줄 인자 네임스페이스입니다.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default=current_platform_id())
    parser.add_argument("--build-dir", default="build/nuitka")
    parser.add_argument("--stage-dir", default="build/standalone")
    parser.add_argument("--output-dir", default="dist/standalone")
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def run(command: list[str]) -> None:
    """릴리스 빌드 명령을 저장소 루트에서 실행하고 실패 시 종료 코드와 명령 문자열을 포함한 오류를 발생시킵니다.

    Args:
        command (list[str]): 하위 프로세스로 실행할 빌드 명령과 인자 목록입니다.
    """
    env = os.environ.copy()
    env.setdefault("NUITKA_CACHE_DIR", str(ROOT / "build" / "nuitka-cache"))
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, check=False)
    if result.returncode != 0:
        raise JudgeError(f"command failed with exit code {result.returncode}: {' '.join(command)}")


def find_nuitka_dist(build_dir: Path) -> Path:
    """Nuitka 빌드 디렉터리에서 가장 최근에 생성된 `.dist` 디렉터리를 찾습니다.

    Args:
        build_dir (Path): Nuitka 산출물이 생성되는 빌드 디렉터리입니다.

    Returns:
        Path: 스테이징에 사용할 Nuitka standalone 배포 디렉터리입니다.
    """
    candidates = sorted(
        [path for path in build_dir.rglob("*.dist") if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise JudgeError(f"Nuitka distribution directory not found under {build_dir}")
    return candidates[0]


def write_checksums(app_root: Path) -> None:
    """스테이징된 앱 루트의 모든 일반 파일에 대해 SHA-256 체크섬 파일을 생성합니다.

    Args:
        app_root (Path): checksums.txt를 기록할 독립 실행 앱 루트 디렉터리입니다.
    """
    entries = []
    for path in sorted(item for item in app_root.rglob("*") if item.is_file()):
        if path.name == "checksums.txt":
            continue
        entries.append(f"{sha256_file(path)}  {path.relative_to(app_root).as_posix()}")
    (app_root / "checksums.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")


def copy_optional_docs(app_root: Path) -> None:
    """배포판 루트에 포함할 사용자 문서가 저장소에 존재하면 함께 복사합니다.

    Args:
        app_root (Path): 문서를 복사할 독립 실행 앱 루트 디렉터리입니다.
    """
    for name in ["README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"]:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, app_root / name)


def create_archive(app_root: Path, output_dir: Path, platform_id: str) -> Path:
    """스테이징된 앱 루트를 버전과 플랫폼 식별자를 포함한 tar.gz 아카이브로 압축합니다.

    Args:
        app_root (Path): 압축할 독립 실행 앱 루트 디렉터리입니다.
        output_dir (Path): 완성된 아카이브를 기록할 출력 디렉터리입니다.
        platform_id (str): 파일명에 포함할 릴리스 플랫폼 식별자입니다.

    Returns:
        Path: 생성된 standalone tar.gz 아카이브 경로입니다.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{APP_DIR_NAME}-{__version__}-{platform_id}.tar.gz"
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(app_root, arcname=APP_DIR_NAME)
    return archive_path


def nuitka_command(build_dir: Path) -> list[str]:
    """두 웹 앱과 정적 자산을 포함하는 Nuitka 빌드 명령을 구성합니다.

    Args:
        build_dir (Path): Nuitka 산출물을 기록할 디렉터리입니다.

    Returns:
        list[str]: 저장소 루트에서 실행할 Nuitka 명령입니다.
    """
    return [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=standalone",
        "--assume-yes-for-downloads",
        "--python-flag=no_docstrings",
        "--python-flag=no_asserts",
        "--include-module=yaml",
        "--include-package=problem_studio",
        f"--include-data-dir=judge/web/static={JUDGE_STATIC_DESTINATION}",
        f"--include-data-dir=problem_studio/web/static={STUDIO_STATIC_DESTINATION}",
        "--output-filename=judge",
        f"--output-dir={build_dir}",
        "alj_launcher/__main__.py",
    ]


def platform_executable_suffix(platform_id: str | None = None) -> str:
    """Return the executable suffix required by a release platform."""
    if platform_id is None:
        return executable_suffix()
    return ".exe" if platform_id.startswith("windows-") else ""


def validate_build_platform(requested: str, current: str) -> None:
    """Reject unsupported targets and accidental cross-platform builds before Nuitka runs."""
    if requested not in SUPPORTED_PLATFORMS:
        raise JudgeError(f"unsupported standalone platform: {requested}")
    if requested != current:
        raise JudgeError(
            "cross-platform standalone build is not implemented; "
            f"current platform is {current}, requested {requested}"
        )


def install_compatibility_launcher(bin_dir: Path, platform_id: str | None = None) -> Path:
    """Judge 실행 파일과 같은 런타임을 쓰는 `problem-studio` 실행기를 만듭니다.

    Args:
        bin_dir (Path): standalone 실행 파일과 런타임 파일이 있는 디렉터리입니다.

    Returns:
        Path: 생성된 Problem Studio 호환 실행기 경로입니다.
    """
    suffix = platform_executable_suffix(platform_id)
    judge_executable = bin_dir / f"judge{suffix}"
    if not judge_executable.is_file():
        raise JudgeError(f"standalone executable not found: {judge_executable}")
    studio_executable = bin_dir / f"problem-studio{suffix}"
    shutil.copy2(judge_executable, studio_executable)
    studio_executable.chmod(studio_executable.stat().st_mode | 0o755)
    return studio_executable


def validate_staged_bundle(app_root: Path, platform_id: str | None = None) -> None:
    """아카이브 생성 전에 두 실행기와 두 웹 UI 핵심 자산의 누락을 검사합니다.

    Args:
        app_root (Path): 검사할 standalone 앱 루트입니다.
    """
    suffix = platform_executable_suffix(platform_id)
    required = [
        Path("bin") / f"judge{suffix}",
        Path("bin") / f"problem-studio{suffix}",
        Path("bin/web/static/index.html"),
        Path("bin/web/static/app.js"),
        Path("bin/studio-web/static/index.html"),
        Path("bin/studio-web/static/app.js"),
        Path("bin/studio-web/static/vendor/codemirror/codemirror.min.js"),
    ]
    missing = [path.as_posix() for path in required if not (app_root / path).is_file()]
    if missing:
        raise JudgeError(f"standalone bundle missing required file(s): {', '.join(missing)}")


def build_standalone(args: argparse.Namespace) -> Path:
    """현재 플랫폼용 Nuitka standalone 앱을 빌드하고 실행 파일, 문서, 체크섬을 스테이징한 뒤 릴리스 아카이브를 만듭니다.

    Args:
        args (argparse.Namespace): standalone 빌드 명령줄 옵션입니다.

    Returns:
        Path: 생성된 standalone 릴리스 아카이브 경로입니다.
    """
    current_platform = current_platform_id()
    validate_build_platform(args.platform, current_platform)

    build_dir = (ROOT / args.build_dir).resolve()
    stage_root = (ROOT / args.stage_dir / args.platform).resolve()
    output_dir = (ROOT / args.output_dir).resolve()
    if args.clean:
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(stage_root, ignore_errors=True)

    build_dir.mkdir(parents=True, exist_ok=True)
    run(nuitka_command(build_dir))

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

    suffix = platform_executable_suffix(args.platform)
    expected_executable = bin_dir / f"judge{suffix}"
    if not expected_executable.exists():
        bin_executable = bin_dir / "judge.bin"
        if bin_executable.exists():
            bin_executable.rename(expected_executable)
    if not expected_executable.exists():
        raise JudgeError(f"standalone executable not found: {expected_executable}")
    expected_executable.chmod(expected_executable.stat().st_mode | 0o755)
    install_compatibility_launcher(bin_dir, args.platform)

    copy_optional_docs(app_root)
    validate_staged_bundle(app_root, args.platform)
    write_checksums(app_root)
    return create_archive(app_root, output_dir, args.platform)


def main() -> int:
    """standalone 빌드를 실행하고 사용자에게 성공 경로 또는 오류 메시지를 출력합니다.

    Returns:
        int: 성공하면 0, 빌드 검증 오류가 발생하면 1입니다.
    """
    try:
        archive_path = build_standalone(parse_args())
    except JudgeError as exc:
        print(f"error: {exc}")
        return 1
    print(f"Built standalone archive: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
