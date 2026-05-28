"""service_runs 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import contextlib
import io
import queue
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO

from judge.core.artifacts import wrong_artifacts, wrong_diff_text
from judge.core.errors import JudgeError
from judge.core.paths import cache_root, rel, validate_safe_id
from judge.core.submission import run_submission
from judge.utils.fs import read_json
from judge.utils.text import format_size
from judge.web.service_common import (
    ARTIFACT_PREVIEW_LIMIT,
    FULL_PROFILE,
    SSE_DONE,
    format_duration,
    language_from_filename,
    sse,
)
from judge.web.service_sources import (
    attach_run_to_source,
    save_text_source,
    save_uploaded_source,
    source_path_from_request,
)


def enrich_run_result(
    result: dict[str, Any],
    run_dir: Path | None = None,
    source: Path | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """enrich_run_result 함수를 실행하고 결과를 반환합니다.
    
    Args:
        result (dict[str, Any]): `result` 값입니다.
        run_dir (Path | None): `run_dir` 값입니다.
        source (Path | None): `source` 값입니다.
        message (str | None): 메시지입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    result = dict(result)
    first_failed = next((case for case in result.get("cases", []) if case["status"] != "ok"), None)
    metrics = result.get("metrics") or {}
    max_time_ms = metrics.get("maxTimeMs")
    max_memory_bytes = metrics.get("maxMemoryBytes")
    if isinstance(max_time_ms, int):
        metrics["maxTimeLabel"] = format_duration(max_time_ms)
    if isinstance(max_memory_bytes, int):
        metrics["maxMemoryLabel"] = format_size(max_memory_bytes)
    else:
        metrics["maxMemoryLabel"] = "Unavailable"
    if run_dir is not None:
        result["runDir"] = str(run_dir)
        result["runLabel"] = rel(run_dir)
    if source is not None:
        result["language"] = result.get("language") or language_from_filename(source.name)
    if message is not None:
        result["message"] = message.strip()
    result["firstFailedCase"] = first_failed["case"] if first_failed else None
    result["metrics"] = metrics
    return result


def build_run_result(run_dir: Path, source: Path, message: str) -> dict[str, Any]:
    """build_run_result 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_dir (Path): `run_dir` 값입니다.
        source (Path): `source` 값입니다.
        message (str): 메시지입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    result = enrich_run_result(read_json(run_dir / "result.json"), run_dir, source, message)
    source_id = attach_run_to_source(source, result)
    if source_id is not None:
        result["sourceId"] = source_id
    return result


def resolve_run_profile(profile: str | None) -> str:
    """resolve_run_profile 함수를 실행하고 결과를 반환합니다.
    
    Args:
        profile (str | None): `profile` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    normalized = (profile or "").strip()
    return normalized or FULL_PROFILE


def run_problem(
    problem_id: str,
    profile: str | None,
    source_mode: str,
    source_path: str | None,
    source_text: str | None,
    filename: str | None,
) -> dict[str, Any]:
    """run_problem 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
        source_mode (str): `source_mode` 값입니다.
        source_path (str | None): `source_path` 값입니다.
        source_text (str | None): `source_text` 값입니다.
        filename (str | None): `filename` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    source = source_path_from_request(problem_id, source_mode, source_path, source_text, filename)
    run_profile = resolve_run_profile(profile)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        run_dir = run_submission(source, problem_id, run_profile)
    return build_run_result(run_dir, source, output.getvalue())


def run_problem_source_with_progress(
    problem_id: str,
    profile: str | None,
    source: Path,
    progress,
) -> dict[str, Any]:
    """run_problem_source_with_progress 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
        source (Path): `source` 값입니다.
        progress (Any): `progress` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    run_profile = resolve_run_profile(profile)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        run_dir = run_submission(source, problem_id, run_profile, progress=progress)
    return build_run_result(run_dir, source, output.getvalue())


def run_uploaded_problem(
    problem_id: str,
    profile: str | None,
    file_obj: BinaryIO,
    filename: str | None,
) -> dict[str, Any]:
    """run_uploaded_problem 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
        file_obj (BinaryIO): `file_obj` 값입니다.
        filename (str | None): `filename` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    source = save_uploaded_source(file_obj, filename, problem_id)
    return run_problem(problem_id, profile, "upload", str(source), None, None)


def run_problem_events(
    problem_id: str,
    profile: str | None,
    source: Path,
) -> Iterator[str]:
    """run_problem_events 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
        source (Path): `source` 값입니다.
    
    Returns:
        Iterator[str]: 처리 결과를 반환합니다.
    """
    events: queue.Queue[dict[str, Any] | object] = queue.Queue()

    def progress(message: str) -> None:
    """progress 함수를 실행하고 결과를 반환합니다.
    
    Args:
        message (str): 메시지입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
        events.put({"event": "log", "data": {"message": message}})

    def worker() -> None:
    """worker 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
        output = io.StringIO()
        try:
            run_profile = resolve_run_profile(profile)
            progress("Starting judge run.")
            with contextlib.redirect_stdout(output):
                run_dir = run_submission(source, problem_id, run_profile, progress=progress)
            result = build_run_result(run_dir, source, output.getvalue())
            events.put({"event": "result", "data": result})
        except Exception as exc:
            events.put({"event": "error", "data": {"message": str(exc)}})
        finally:
            events.put(SSE_DONE)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = events.get()
        if item is SSE_DONE:
            break
        if isinstance(item, dict):
            yield sse(str(item["event"]), item["data"])


def save_source_for_stream(
    source_mode: str,
    file_obj: BinaryIO | None,
    upload_filename: str | None,
    source_text: str | None,
    text_filename: str | None,
    problem_id: str,
) -> Path:
    """save_source_for_stream 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source_mode (str): `source_mode` 값입니다.
        file_obj (BinaryIO | None): `file_obj` 값입니다.
        upload_filename (str | None): `upload_filename` 값입니다.
        source_text (str | None): `source_text` 값입니다.
        text_filename (str | None): `text_filename` 값입니다.
        problem_id (str): 문제 ID입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if source_mode == "upload":
        if file_obj is None:
            raise JudgeError("source file upload is required")
        return save_uploaded_source(file_obj, upload_filename, problem_id)
    if source_mode == "text":
        if not source_text:
            raise JudgeError("source text is required")
        return save_text_source(source_text, text_filename, problem_id)
    raise JudgeError(f"unsupported source mode: {source_mode}")


def run_result(run_id: str) -> dict[str, Any]:
    """run_result 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_id (str): `run_id` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    validate_safe_id("run id", run_id)
    run_dir = cache_root() / "runs" / run_id
    result_path = run_dir / "result.json"
    if not result_path.exists():
        raise JudgeError(f"run result not found: {run_id}")
    return enrich_run_result(read_json(result_path), run_dir)


def preview_artifact_text(text: str, limit: int = ARTIFACT_PREVIEW_LIMIT) -> dict[str, Any]:
    """preview_artifact_text 함수를 실행하고 결과를 반환합니다.
    
    Args:
        text (str): `text` 값입니다.
        limit (int): `limit` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    if len(text) <= limit:
        return {"text": text, "truncated": False, "omittedChars": 0}
    omitted = len(text) - limit
    preview = text[:limit].rstrip()
    preview += f"\n\n... truncated after {limit} chars, omitted {omitted} chars ..."
    return {"text": preview, "truncated": True, "omittedChars": omitted}


def wrong_case(run_id: str, case_id: str) -> dict[str, Any]:
    """wrong_case 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_id (str): `run_id` 값입니다.
        case_id (str): `case_id` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    raw_data = wrong_artifacts(run_id, case_id)
    raw_data["diff"] = wrong_diff_text(run_id, case_id)
    result: dict[str, Any] = {"previewLimit": ARTIFACT_PREVIEW_LIMIT, "truncation": {}}
    for key, value in raw_data.items():
        preview = preview_artifact_text(value)
        result[key] = preview["text"]
        result["truncation"][key] = {
            "truncated": preview["truncated"],
            "omittedChars": preview["omittedChars"],
        }
    return result
