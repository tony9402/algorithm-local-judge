"""Generate a release-specific Homebrew formula with immutable asset digests."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

REPOSITORY = "tony9402/algorithm-local-judge"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def version_from_tag(tag: str) -> str:
    version = tag.removeprefix("v")
    if not version or any(character not in "0123456789." for character in version):
        raise ValueError(f"release tag must be v<numeric-version>: {tag}")
    return version


def asset(assets: Path, version: str, platform: str) -> Path:
    path = assets / f"algorithm-local-judge-{version}-{platform}.tar.gz"
    if not path.is_file():
        raise ValueError(f"standalone release asset not found: {path}")
    return path


def formula_text(assets: Path, tag: str) -> str:
    version = version_from_tag(tag)
    base = f"https://github.com/{REPOSITORY}/releases/download/{tag}"
    mac_arm = asset(assets, version, "macos-arm64")
    mac_intel = asset(assets, version, "macos-amd64")
    linux = asset(assets, version, "linux-amd64")
    return f'''class AlgorithmLocalJudge < Formula
  desc "Local web judge and problem authoring studio"
  homepage "https://github.com/{REPOSITORY}"
  version "{version}"

  on_macos do
    if Hardware::CPU.arm?
      url "{base}/{mac_arm.name}"
      sha256 "{sha256(mac_arm)}"
    else
      url "{base}/{mac_intel.name}"
      sha256 "{sha256(mac_intel)}"
    end
  end

  on_linux do
    url "{base}/{linux.name}"
    sha256 "{sha256(linux)}"
  end

  def install
    libexec.install "algorithm-local-judge"
    bin.install_symlink libexec/"algorithm-local-judge/bin/judge"
    bin.install_symlink libexec/"algorithm-local-judge/bin/problem-studio"
  end

  test do
    assert_match "usage: judge", shell_output("#{{bin}}/judge --help")
    assert_match "usage: problem-studio", shell_output("#{{bin}}/problem-studio --help")
    system bin/"judge", "setup", "--check-only"
  end
end
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        content = formula_text(args.assets.resolve(), args.tag)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Built Homebrew formula: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
