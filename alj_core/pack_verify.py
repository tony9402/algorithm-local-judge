"""문제팩 verify 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from alj_core.errors import JudgeError
from alj_core.pack_archive import (
    PACK_SCHEMA_VERSION,
    reject_forbidden_release_file,
    safe_extract_tar,
    single_pack_dir,
)
from alj_core.paths import validate_safe_id
from alj_core.utils.fs import read_json
from alj_core.utils.hashing import sha256_file


def verify_pack_dir(pack_dir: Path) -> dict[str, Any]:
    pack_json = pack_dir / "pack.json"
    manifest_json = pack_dir / "manifest.json"
    if not pack_json.exists():
        raise JudgeError("pack.json not found in problem pack")
    if not manifest_json.exists():
        raise JudgeError("manifest.json not found in problem pack")
    pack = read_json(pack_json)
    manifest = read_json(manifest_json)
    if pack.get("schemaVersion") != PACK_SCHEMA_VERSION:
        raise JudgeError(f"unsupported pack schema version: {pack.get('schemaVersion')}")
    if manifest.get("schemaVersion") != PACK_SCHEMA_VERSION:
        raise JudgeError(f"unsupported manifest schema version: {manifest.get('schemaVersion')}")
    validate_safe_id("pack id", pack.get("packId", ""))
    for path in pack_dir.rglob("*"):
        if path.is_file():
            reject_forbidden_release_file(path)
    expected_files = {entry["path"]: entry["sha256"] for entry in manifest.get("files", [])}
    if not expected_files:
        raise JudgeError("problem pack manifest has no file entries")
    for relative, expected_hash in expected_files.items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise JudgeError(f"unsafe path in pack manifest: {relative}")
        path = pack_dir / relative
        if not path.exists():
            raise JudgeError(f"manifest file missing: {relative}")
        if sha256_file(path) != expected_hash:
            raise JudgeError(f"manifest hash mismatch: {relative}")
    return pack


def verify_pack(archive_path: Path) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    if not archive_path.exists():
        raise JudgeError(f"problem pack not found: {archive_path}")
    with tempfile.TemporaryDirectory(prefix="alj-pack-verify-") as tmp:
        extracted_dir = Path(tmp)
        safe_extract_tar(archive_path, extracted_dir)
        return verify_pack_dir(single_pack_dir(extracted_dir))
