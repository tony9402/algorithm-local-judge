"""source_history_metadata 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path
from typing import Any

from judge.core.paths import rel
from judge.utils.fs import read_json, write_json
from judge.utils.text import format_size
from judge.web.service_common import format_duration, language_from_filename


def source_history_metadata(
    source_id: str,
    target: Path,
    problem_id: str,
    source_mode: str,
) -> dict[str, Any]:
    """source_history_metadata 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source_id (str): 소스 ID입니다.
        target (Path): `target` 값입니다.
        problem_id (str): 문제 ID입니다.
        source_mode (str): `source_mode` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    stat = target.stat()
    saved_at = stat.st_mtime
    return {
        "sourceId": source_id,
        "problemId": problem_id,
        "sourceMode": source_mode,
        "filename": target.name,
        "language": language_from_filename(target.name),
        "savedAt": saved_at,
        "size": stat.st_size,
        "sizeLabel": format_size(stat.st_size),
        "sourcePath": str(target),
        "sourceLabel": rel(target),
    }


def write_source_history_metadata(
    source_id: str,
    target: Path,
    problem_id: str,
    source_mode: str,
) -> dict[str, Any]:
    """write_source_history_metadata 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source_id (str): 소스 ID입니다.
        target (Path): `target` 값입니다.
        problem_id (str): 문제 ID입니다.
        source_mode (str): `source_mode` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    metadata = source_history_metadata(source_id, target, problem_id, source_mode)
    write_json(target.parent / "metadata.json", metadata)
    return metadata


def source_history_run_summary(result: dict[str, Any]) -> dict[str, Any]:
    """source_history_run_summary 함수를 실행하고 결과를 반환합니다.
    
    Args:
        result (dict[str, Any]): `result` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    cases = result.get("cases") if isinstance(result.get("cases"), list) else []
    return {
        "runId": result.get("runId"),
        "problemId": result.get("problemId"),
        "profile": result.get("profile"),
        "language": result.get("language"),
        "status": result.get("status"),
        "caseCount": len(cases),
        "firstFailedCase": result.get("firstFailedCase"),
        "metrics": result.get("metrics") or {},
        "runLabel": result.get("runLabel"),
        "savedAt": time.time(),
    }


def source_file_for_entry(entry_dir: Path, metadata: dict[str, Any] | None) -> Path | None:
    """source_file_for_entry 함수를 실행하고 결과를 반환합니다.
    
    Args:
        entry_dir (Path): `entry_dir` 값입니다.
        metadata (dict[str, Any] | None): `metadata` 값입니다.
    
    Returns:
        Path | None: 처리 결과를 반환합니다.
    """
    if metadata:
        filename = Path(str(metadata.get("filename", ""))).name
        if filename:
            candidate = entry_dir / filename
            if candidate.exists() and candidate.is_file():
                return candidate
    for candidate in sorted(entry_dir.iterdir()):
        if candidate.is_file() and candidate.name != "metadata.json":
            return candidate
    return None


def source_entry_metadata(entry_dir: Path) -> dict[str, Any] | None:
    """source_entry_metadata 함수를 실행하고 결과를 반환합니다.
    
    Args:
        entry_dir (Path): `entry_dir` 값입니다.
    
    Returns:
        dict[str, Any] | None: 처리 결과를 반환합니다.
    """
    source_id = entry_dir.name
    metadata_path = entry_dir / "metadata.json"
    metadata = None
    if metadata_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            loaded_metadata = read_json(metadata_path)
            if isinstance(loaded_metadata, dict):
                metadata = loaded_metadata
    source_file = source_file_for_entry(entry_dir, metadata)
    if source_file is None:
        return None
    if metadata is None:
        metadata = source_history_metadata(source_id, source_file, "unknown", "unknown")
    else:
        metadata = dict(metadata)
        metadata["sourceId"] = source_id
        metadata["filename"] = source_file.name
        metadata["language"] = metadata.get("language") or language_from_filename(source_file.name)
        metadata["size"] = source_file.stat().st_size
        metadata["sizeLabel"] = format_size(source_file.stat().st_size)
        metadata["sourcePath"] = str(source_file)
        metadata["sourceLabel"] = rel(source_file)
        last_run = metadata.get("lastRun")
        if isinstance(last_run, dict):
            metrics = last_run.get("metrics")
            if isinstance(metrics, dict):
                max_time_ms = metrics.get("maxTimeMs")
                max_memory_bytes = metrics.get("maxMemoryBytes")
                if isinstance(max_time_ms, int):
                    metrics["maxTimeLabel"] = format_duration(max_time_ms)
                if isinstance(max_memory_bytes, int):
                    metrics["maxMemoryLabel"] = format_size(max_memory_bytes)
    return metadata
