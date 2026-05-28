"""소스 이력 store 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
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
    """uploaded 소스 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        file_obj (BinaryIO): uploaded 소스을 계산하거나 검증할 때 필요한 파일 obj 입력입니다.
        filename (str | None): 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.

    Returns:
        Path: 검증된 uploaded 소스 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
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
    """텍스트 소스 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        source_text (str): 요청 본문으로 전달된 제출 소스 코드입니다.
        filename (str | None): 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.

    Returns:
        Path: 검증된 텍스트 소스 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
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
    """existing 소스 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        path (Path): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        source_mode (str): 소스가 경로, 업로드, 직접 입력 중 어떤 방식으로 전달됐는지 나타냅니다.

    Returns:
        Path: 검증된 existing 소스 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
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
    """현재 설정과 파일시스템을 기준으로 소스 이력 목록을 조회합니다.

    Args:
        limit (int): 소스 이력을 계산하거나 검증할 때 필요한 제한 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 소스 이력 데이터입니다.
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
    """소스 이력 파일이나 상태 항목을 안전성 검사를 거쳐 제거합니다.

    Args:
        source_id (str): 소스 ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 소스 이력 데이터입니다.
    """
    entry_dir = source_entry_dir(source_id)
    if not entry_dir.exists():
        raise JudgeError(f"source history entry not found: {source_id}")
    shutil.rmtree(entry_dir)
    return {"deleted": True, "sourceId": source_id}
