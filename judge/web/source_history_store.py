"""source_history_store 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import contextlib
import json
import shutil
from pathlib import Path
from typing import Any, BinaryIO

from judge.core import security_limits
from judge.core.errors import JudgeError
from judge.core.paths import ensure_inside
from judge.utils.fs import write_json
from judge.utils.limited_io import copy_limited, write_text_limited
from judge.web.service_common import SOURCE_HISTORY_LIMIT
from judge.web.source_history_metadata import (
    source_entry_metadata,
    source_file_for_entry,
    source_history_metadata,
    source_history_run_summary,
    write_source_history_metadata,
)
from judge.web.source_history_paths import (
    create_source_target,
    source_entry_dir,
    source_history_root,
    source_id_from_path,
)


def attach_run_to_source(source: Path, result: dict[str, Any]) -> str | None:
    """attach_run_to_source 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (Path): `source` 값입니다.
        result (dict[str, Any]): `result` 값입니다.
    
    Returns:
        str | None: 처리 결과를 반환합니다.
    """
    source_id = source_id_from_path(source)
    if source_id is None:
        return None
    entry_dir = source_entry_dir(source_id)
    metadata = source_entry_metadata(entry_dir) or source_history_metadata(
        source_id,
        source,
        str(result.get("problemId") or "unknown"),
        "unknown",
    )
    metadata["lastRun"] = source_history_run_summary(result)
    write_json(entry_dir / "metadata.json", metadata)
    return source_id


def save_uploaded_source(
    file_obj: BinaryIO,
    filename: str | None,
    problem_id: str,
) -> Path:
    """save_uploaded_source 함수를 실행하고 결과를 반환합니다.
    
    Args:
        file_obj (BinaryIO): `file_obj` 값입니다.
        filename (str | None): `filename` 값입니다.
        problem_id (str): 문제 ID입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    source_id, target = create_source_target(problem_id, filename or "main.py")
    try:
        copy_limited(
            file_obj,
            target,
            limit_bytes=security_limits.MAX_SOURCE_UPLOAD_BYTES,
            label="source upload",
        )
        if target.stat().st_size == 0:
            raise JudgeError("uploaded source file is empty")
        write_source_history_metadata(source_id, target, problem_id, "upload")
    except Exception:
        shutil.rmtree(target.parent, ignore_errors=True)
        raise
    return target


def save_text_source(source_text: str, filename: str | None, problem_id: str) -> Path:
    """save_text_source 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source_text (str): `source_text` 값입니다.
        filename (str | None): `filename` 값입니다.
        problem_id (str): 문제 ID입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    source_id, target = create_source_target(problem_id, filename)
    try:
        write_text_limited(
            source_text,
            target,
            limit_bytes=security_limits.MAX_SOURCE_TEXT_BYTES,
            label="source text",
        )
        write_source_history_metadata(source_id, target, problem_id, "text")
    except Exception:
        shutil.rmtree(target.parent, ignore_errors=True)
        raise
    return target


def save_existing_source(path: Path, problem_id: str, source_mode: str) -> Path:
    """save_existing_source 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
        problem_id (str): 문제 ID입니다.
        source_mode (str): `source_mode` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    source_id, target = create_source_target(problem_id, path.name)
    try:
        with path.open("rb") as source:
            copy_limited(
                source,
                target,
                limit_bytes=security_limits.MAX_SOURCE_UPLOAD_BYTES,
                label="source file",
            )
        if target.stat().st_size == 0:
            raise JudgeError("source file is empty")
        write_source_history_metadata(source_id, target, problem_id, source_mode)
    except Exception:
        shutil.rmtree(target.parent, ignore_errors=True)
        raise
    return target


def list_source_history(limit: int = SOURCE_HISTORY_LIMIT) -> dict[str, Any]:
    """list_source_history 함수를 실행하고 결과를 반환합니다.
    
    Args:
        limit (int): `limit` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    root = source_history_root()
    if not root.exists():
        return {"sources": []}
    entries = []
    for entry_dir in sorted(root.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True):
        if not entry_dir.is_dir():
            continue
        metadata = source_entry_metadata(entry_dir)
        if metadata is not None:
            entries.append(metadata)
        if len(entries) >= limit:
            break
    return {"sources": entries}


def source_history_detail(source_id: str) -> dict[str, Any]:
    """source_history_detail 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source_id (str): 소스 ID입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    entry_dir = source_entry_dir(source_id)
    if not entry_dir.exists():
        raise JudgeError(f"source history entry not found: {source_id}")
    metadata = source_entry_metadata(entry_dir)
    if metadata is None:
        raise JudgeError(f"source history entry has no source file: {source_id}")
    source_file = source_file_for_entry(entry_dir, metadata)
    if source_file is None:
        raise JudgeError(f"source history entry has no source file: {source_id}")
    source_file = ensure_inside(source_file, source_history_root())
    last_run_result = None
    last_run = metadata.get("lastRun")
    if isinstance(last_run, dict) and isinstance(last_run.get("runId"), str):
        with contextlib.suppress(JudgeError, json.JSONDecodeError, OSError):
            from judge.web.service_runs import run_result

            last_run_result = run_result(last_run["runId"])
    return {
        **metadata,
        "lastRunResult": last_run_result,
        "sourceText": source_file.read_text(encoding="utf-8", errors="replace"),
    }


def delete_source_history(source_id: str) -> dict[str, Any]:
    """delete_source_history 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source_id (str): 소스 ID입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    entry_dir = source_entry_dir(source_id)
    if not entry_dir.exists():
        raise JudgeError(f"source history entry not found: {source_id}")
    shutil.rmtree(entry_dir)
    return {"deleted": True, "sourceId": source_id}
