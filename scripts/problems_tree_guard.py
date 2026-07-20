"""Capture and verify that tests never mutate the user's problems tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EXCLUDED_DIRECTORY_NAMES = {".git"}


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def capture_tree(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"problems root does not exist: {root}")
    entries: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts):
            continue
        mode = stat.S_IMODE(path.lstat().st_mode)
        label = relative.as_posix()
        if path.is_symlink():
            entries[label] = {
                "type": "symlink",
                "mode": mode,
                "target": path.readlink().as_posix(),
            }
        elif path.is_file():
            entries[label] = {
                "type": "file",
                "mode": mode,
                "size": path.stat().st_size,
                "sha256": file_digest(path),
            }
        elif path.is_dir():
            entries[label] = {"type": "directory", "mode": mode}
    return {"schemaVersion": SCHEMA_VERSION, "root": str(root), "entries": entries}


def write_snapshot(root: Path, snapshot_path: Path) -> None:
    snapshot = capture_tree(root)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def changed_paths(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_entries = before.get("entries") or {}
    after_entries = after.get("entries") or {}
    return [
        path
        for path in sorted(set(before_entries) | set(after_entries))
        if before_entries.get(path) != after_entries.get(path)
    ]


def verify_snapshot(root: Path, snapshot_path: Path) -> list[str]:
    if not snapshot_path.is_file():
        raise ValueError(f"problems snapshot does not exist: {snapshot_path}")
    before = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if before.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("unsupported problems snapshot schema")
    return changed_paths(before, capture_tree(root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail when tests add, modify, delete, chmod, or retarget files under problems/."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("capture", "verify"):
        child = subparsers.add_parser(command)
        child.add_argument("--root", type=Path, default=Path("problems"))
        child.add_argument("--snapshot", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "capture":
            write_snapshot(args.root, args.snapshot)
            print(f"Captured immutable problems tree: {args.root}")
            return 0
        changes = verify_snapshot(args.root, args.snapshot)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"problems guard error: {exc}", file=sys.stderr)
        return 2
    if changes:
        print(
            "problems tree was modified; tests must use isolated temporary workspaces:",
            file=sys.stderr,
        )
        for path in changes[:100]:
            print(f"  {path}", file=sys.stderr)
        if len(changes) > 100:
            print(f"  ... and {len(changes) - 100} more", file=sys.stderr)
        return 1
    print("Verified immutable problems tree: no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
