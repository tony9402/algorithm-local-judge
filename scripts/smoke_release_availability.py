"""Revalidate a directory downloaded from a published release."""

from __future__ import annotations

import argparse
from pathlib import Path

from judge.core.errors import JudgeError

try:
    from scripts.validate_release_manifest import validate_release_manifest
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from validate_release_manifest import validate_release_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    root = args.assets.resolve()
    manifest = root / "release-manifest.json"
    try:
        validate_release_manifest(
            manifest,
            root,
            stable=True,
            require_manifest_sidecars=True,
        )
    except JudgeError as exc:
        print(f"error: published release availability smoke failed: {exc}")
        return 1
    print(f"Published release assets are complete: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
