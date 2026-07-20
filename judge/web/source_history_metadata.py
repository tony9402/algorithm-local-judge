"""소스 이력 메타데이터 웹 백엔드 구성과 응답 데이터 조립을 담당합니다."""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path
from typing import Any

from judge.core.paths import rel
from judge.utils.fs import read_json, write_json
from judge.utils.text import format_size
from judge.web.service_common import (
    format_duration,
    language_display,
    language_from_filename,
    language_id_from_filename,
    normalize_language_id,
)


def source_history_metadata(
    source_id: str,
    target: Path,
    problem_id: str,
    source_mode: str,
    language: str | None = None,
) -> dict[str, Any]:
    stat = target.stat()
    saved_at = stat.st_mtime
    language_id = normalize_language_id(language) or language_id_from_filename(target.name)
    return {
        "sourceId": source_id,
        "problemId": problem_id,
        "sourceMode": source_mode,
        "filename": target.name,
        "language": language_display(language_id)
        if language_id
        else language_from_filename(target.name),
        "languageId": language_id,
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
    language: str | None = None,
) -> dict[str, Any]:
    """소스 이력 메타데이터 데이터를 지정된 파일이나 응답 대상에 기록합니다.

    Args:
        source_id (str): 소스 ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.
        target (Path): 파일을 복사하거나 산출물을 배치할 대상 경로입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        source_mode (str): 소스가 경로, 업로드, 직접 입력 중 어떤 방식으로 전달됐는지 나타냅니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 소스 이력 메타데이터 데이터입니다.
    """
    metadata = source_history_metadata(source_id, target, problem_id, source_mode, language)
    write_json(target.parent / "metadata.json", metadata)
    return metadata


def source_history_run_summary(result: dict[str, Any]) -> dict[str, Any]:
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
        language_id = normalize_language_id(metadata.get("languageId") or metadata.get("language"))
        language_id = language_id or language_id_from_filename(source_file.name)
        metadata["languageId"] = language_id
        metadata["language"] = (
            language_display(language_id)
            if language_id
            else language_from_filename(source_file.name)
        )
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
