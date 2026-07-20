"""fs 기능을 담당하는 모듈입니다."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    """json을 외부 입력에서 읽어 호출자가 바로 사용할 값으로 변환합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
    """
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    """json 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
        data (Any): 파일, API 응답, UI 렌더링에 사용할 구조화된 데이터입니다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def transactional_replace_directory(source: Path, target: Path) -> None:
    """검증된 directory를 target에 atomic하게 교체하고 실패 시 이전 상태를 복구합니다."""
    source = source.resolve()
    target = Path(target)
    if target.is_symlink():
        raise ValueError(f"refusing to replace symlink target: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    incoming = target.with_name(f".{target.name}.incoming-{uuid.uuid4().hex}")
    backup = target.with_name(f".{target.name}.backup-{uuid.uuid4().hex}")
    old_exists = target.exists()
    try:
        shutil.copytree(source, incoming)
        if old_exists:
            os.replace(target, backup)
        os.replace(incoming, target)
    except Exception:
        if incoming.exists():
            shutil.rmtree(incoming, ignore_errors=True)
        if old_exists and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    finally:
        if incoming.exists():
            shutil.rmtree(incoming, ignore_errors=True)
        if backup.exists() and target.exists():
            shutil.rmtree(backup, ignore_errors=True)
