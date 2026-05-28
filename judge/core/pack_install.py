"""문제팩 설치 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.pack_archive import safe_extract_tar, single_pack_dir
from judge.core.pack_verify import verify_pack_dir
from judge.core.paths import problem_pack_root, validate_safe_id
from judge.utils.fs import read_json


def install_pack(archive_path: Path) -> Path:
    """설치 문제팩 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        archive_path (Path): 아카이브 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.

    Returns:
        Path: 검증된 설치 문제팩 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    archive_path = archive_path.resolve()
    with tempfile.TemporaryDirectory(prefix="alj-pack-install-") as tmp:
        extracted_dir = Path(tmp)
        safe_extract_tar(archive_path, extracted_dir)
        staged_pack_dir = single_pack_dir(extracted_dir)
        pack = verify_pack_dir(staged_pack_dir)
        target = problem_pack_root() / pack["packId"]
        backup = None
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = target.with_name(target.name + ".old")
            if backup.exists():
                shutil.rmtree(backup)
            target.rename(backup)
        shutil.copytree(staged_pack_dir, target)
        if backup is not None:
            shutil.rmtree(backup)
        return target


def installed_packs() -> list[dict[str, Any]]:
    root = problem_pack_root()
    if not root.exists():
        return []
    packs = []
    for pack_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        pack_json = pack_dir / "pack.json"
        if pack_json.exists():
            pack = read_json(pack_json)
            pack["path"] = str(pack_dir)
            packs.append(pack)
    return packs


def remove_pack(pack_id: str) -> Path:
    """문제팩 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        pack_id (str): 설치, 삭제, 조회할 문제팩을 구분하는 ID입니다.

    Returns:
        Path: 검증된 문제팩 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    validate_safe_id("pack id", pack_id)
    target = problem_pack_root() / pack_id
    if not target.exists():
        raise JudgeError(f"problem pack not installed: {pack_id}")
    shutil.rmtree(target)
    return target
