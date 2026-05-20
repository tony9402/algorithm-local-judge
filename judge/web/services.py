from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import queue
import shutil
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO

from commons.generate import load_config
from judge.core.artifacts import wrong_artifacts, wrong_diff_text
from judge.core.cache import build_cache_clear_plan, cache_status_data, delete_cache_targets
from judge.core.cases_compile import compile_problem_cases
from judge.core.errors import JudgeError
from judge.core.generation import cache_dir_for, generate
from judge.core.manifest import generation_key, validate_manifest_fast
from judge.core.pack import installed_packs
from judge.core.paths import cache_root, ensure_inside, rel, validate_safe_id
from judge.core.problem import discover_problem_ids, load_problem, tool_paths
from judge.core.remote import (
    download_problem_pack_from_github,
    official_pack_repository,
)
from judge.core.remote import (
    install_problem_pack as install_local_problem_pack,
)
from judge.core.submission import run_submission
from judge.utils.fs import read_json, write_json
from judge.utils.text import format_size

SAMPLE_PROFILE = "sample"
HIDDEN_PROFILE = "hidden"
ARTIFACT_PREVIEW_LIMIT = 12000
SOURCE_HISTORY_LIMIT = 50
WEB_DEBUG_ENV = "ALJ_WEB_DEBUG"
SSE_DONE = object()
SAMPLE_RESPONSE_CACHE: dict[str, dict[str, Any]] = {}
SAMPLE_RESPONSE_CACHE_LOCK = threading.Lock()


def language_from_filename(filename: str) -> str:
    """Return a display language from a source filename."""
    suffix = Path(filename).suffix.lower()
    if suffix in {".cpp", ".cc", ".cxx"}:
        return "C++"
    if suffix == ".py":
        return "Python"
    if suffix == ".java":
        return "Java"
    return "Unknown"


def problem_profiles(problem_id: str) -> list[str]:
    """Return profile names declared by a problem generator config."""
    try:
        _, _, _, paths = tool_paths(problem_id)
        config = load_config(paths["generatorConfig"])
    except Exception:
        return []
    profiles = config.get("profiles", {})
    return sorted(profiles) if isinstance(profiles, dict) else []


def list_problems() -> list[dict[str, Any]]:
    """Return problem metadata for the web UI."""
    problems = []
    for problem_id in discover_problem_ids():
        _, _, metadata = load_problem(problem_id)
        problems.append(
            {
                "problemId": problem_id,
                "title": metadata.get("title", ""),
                "version": metadata.get("version"),
                "defaultProfile": metadata.get("defaultProfile", "full"),
                "profiles": problem_profiles(problem_id),
            }
        )
    return problems


def list_packs() -> list[dict[str, Any]]:
    """Return installed problem pack metadata."""
    return installed_packs()


def web_debug_enabled() -> bool:
    """Return whether the web UI should expose debug logs."""
    value = os.environ.get(WEB_DEBUG_ENV, "")
    return value.lower() in {"1", "true", "yes", "on"}


def install_problem_pack(archive_path: str) -> dict[str, Any]:
    """Install a problem pack and return its installed path."""
    return install_local_problem_pack(Path(archive_path))


def safe_upload_name(filename: str | None, fallback: str) -> str:
    """Return a basename-only upload filename."""
    name = Path(filename or fallback).name
    if not name or name in {".", ".."}:
        raise JudgeError("invalid upload filename")
    return name


def save_upload(file_obj: BinaryIO, filename: str | None, category: str, fallback: str) -> Path:
    """Persist an uploaded file under the local judge cache."""
    name = safe_upload_name(filename, fallback)
    target_dir = cache_root() / "web-uploads" / category / str(time.time_ns())
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name
    with target.open("wb") as output:
        shutil.copyfileobj(file_obj, output)
    if target.stat().st_size == 0:
        raise JudgeError("uploaded file is empty")
    return target


def source_history_root() -> Path:
    """Return the cache directory that stores source files submitted from the web UI."""
    return cache_root() / "web-submissions"


def source_entry_dir(source_id: str) -> Path:
    """Return a validated source history entry directory."""
    validate_safe_id("source id", source_id)
    return ensure_inside(source_history_root() / source_id, cache_root())


def create_source_target(problem_id: str, filename: str | None) -> tuple[str, Path]:
    """Create a new source history target path for a submitted source file."""
    validate_safe_id("problem id", problem_id)
    source_id = str(time.time_ns())
    target_dir = source_entry_dir(source_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    return source_id, target_dir / default_filename(problem_id, filename)


def source_history_metadata(
    source_id: str,
    target: Path,
    problem_id: str,
    source_mode: str,
) -> dict[str, Any]:
    """Build metadata for one cached source history entry."""
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
    """Persist metadata next to one cached source file."""
    metadata = source_history_metadata(source_id, target, problem_id, source_mode)
    write_json(target.parent / "metadata.json", metadata)
    return metadata


def source_id_from_path(source: Path) -> str | None:
    """Return the source history id for a cached source path when available."""
    with contextlib.suppress(JudgeError):
        cached_source = ensure_inside(source, source_history_root())
        if cached_source.parent.parent == source_history_root():
            return cached_source.parent.name
    return None


def source_history_run_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Return a compact run summary suitable for source history metadata."""
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


def attach_run_to_source(source: Path, result: dict[str, Any]) -> str | None:
    """Store the latest run result summary beside a cached source file."""
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
    """Persist an uploaded source file in the web source history and return its path."""
    source_id, target = create_source_target(problem_id, filename or "main.py")
    with target.open("wb") as output:
        shutil.copyfileobj(file_obj, output)
    if target.stat().st_size == 0:
        raise JudgeError("uploaded source file is empty")
    write_source_history_metadata(source_id, target, problem_id, "upload")
    return target


def save_text_source(source_text: str, filename: str | None, problem_id: str) -> Path:
    """Persist pasted source code in the web source history and return its path."""
    source_id, target = create_source_target(problem_id, filename)
    target.write_text(source_text, encoding="utf-8")
    write_source_history_metadata(source_id, target, problem_id, "text")
    return target


def save_existing_source(path: Path, problem_id: str, source_mode: str) -> Path:
    """Copy an existing local source file into the web source history."""
    source_id, target = create_source_target(problem_id, path.name)
    shutil.copy2(path, target)
    if target.stat().st_size == 0:
        raise JudgeError("source file is empty")
    write_source_history_metadata(source_id, target, problem_id, source_mode)
    return target


def save_uploaded_pack(file_obj: BinaryIO, filename: str | None) -> Path:
    """Persist an uploaded problem pack and return its path."""
    target = save_upload(file_obj, filename, "packs", "problem-pack.aljpack")
    if target.suffix != ".aljpack":
        raise JudgeError("problem pack upload must have .aljpack extension")
    return target


def install_uploaded_problem_pack(file_obj: BinaryIO, filename: str | None) -> dict[str, Any]:
    """Install an uploaded problem pack file."""
    target = save_uploaded_pack(file_obj, filename)
    result = install_problem_pack(str(target))
    result["uploadedPath"] = str(target)
    return result


def download_official_problem_pack(
    repository: str | None = None,
    asset_name: str | None = None,
) -> dict[str, Any]:
    """Download and install a problem pack from the configured public GitHub repo."""
    return download_problem_pack_from_github(repository, asset_name)


def generate_problem(problem_id: str, profile: str | None, force: bool) -> dict[str, Any]:
    """Generate test data and return a concise result summary."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        data_dir = generate(problem_id, profile, force)
    manifest = read_json(data_dir / "manifest.json")
    return {
        "path": str(data_dir),
        "label": rel(data_dir),
        "profile": manifest.get("profile"),
        "caseCount": len(manifest.get("cases", [])),
        "message": output.getvalue().strip(),
    }


def compile_problem_cases_result(problem_id: str, profile: str | None) -> dict[str, Any]:
    """Compile a problem cases.yml profile and return structured diagnostics."""
    return compile_problem_cases(problem_id, profile).to_dict()


def build_generate_result(data_dir: Path, message: str) -> dict[str, Any]:
    """Build a web response from a generated data directory."""
    manifest = read_json(data_dir / "manifest.json")
    return {
        "path": str(data_dir),
        "label": rel(data_dir),
        "profile": manifest.get("profile"),
        "caseCount": len(manifest.get("cases", [])),
        "message": message.strip(),
    }


def cached_data_dir(problem_id: str, profile: str) -> Path | None:
    """Return a valid generated data cache without invoking generator tools."""
    key = generation_key(problem_id, profile)
    data_dir = cache_dir_for(problem_id, key)
    if validate_manifest_fast(data_dir, problem_id, profile, key):
        return data_dir
    return None


def sample_response_cache_key(data_dir: Path) -> str:
    """Return a cache key for sample response payloads."""
    manifest = data_dir / "manifest.json"
    stat = manifest.stat()
    return f"{data_dir}:{stat.st_mtime_ns}:{stat.st_size}"


def sample_response_etag(data_dir: Path, manifest: dict[str, Any]) -> str:
    """Return an HTTP validator for a generated sample dataset."""
    manifest_path = data_dir / "manifest.json"
    stat = manifest_path.stat()
    parts = [
        "sample",
        str(manifest.get("problemId", "")),
        str(manifest.get("profile", "")),
        str(manifest.get("generationKey", "")),
        str(stat.st_mtime_ns),
        str(stat.st_size),
    ]
    return 'W/"' + "-".join(parts) + '"'


def copy_sample_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a mutable copy of a cached sample response."""
    copied = payload.copy()
    copied["cases"] = [case.copy() for case in payload.get("cases", [])]
    return copied


def build_sample_cases_result(data_dir: Path, message: str, cached: bool) -> dict[str, Any]:
    """Build visible sample input/answer data from a generated data directory."""
    cache_key = sample_response_cache_key(data_dir)
    with SAMPLE_RESPONSE_CACHE_LOCK:
        cached_payload = SAMPLE_RESPONSE_CACHE.get(cache_key)
    if cached_payload is not None:
        result = copy_sample_response(cached_payload)
        result["cached"] = cached
        result["message"] = message
        return result

    manifest = read_json(data_dir / "manifest.json")
    cases = []
    for case in manifest.get("cases", []):
        cases.append(
            {
                "case": case["id"],
                "name": case.get("name") or case["id"],
                "input": (data_dir / case["input"]).read_text(
                    encoding="utf-8",
                    errors="replace",
                ),
                "expected": (data_dir / case["answer"]).read_text(
                    encoding="utf-8",
                    errors="replace",
                ),
            }
        )
    result = {
        "problemId": manifest.get("problemId"),
        "profile": manifest.get("profile", SAMPLE_PROFILE),
        "caseCount": len(cases),
        "label": rel(data_dir),
        "message": message,
        "cached": cached,
        "etag": sample_response_etag(data_dir, manifest),
        "cases": cases,
    }
    with SAMPLE_RESPONSE_CACHE_LOCK:
        SAMPLE_RESPONSE_CACHE[cache_key] = copy.deepcopy(result)
    return result


def sample_cases(problem_id: str, force: bool = False) -> dict[str, Any]:
    """Return visible sample input/answer text, generating only on the first miss."""
    output = io.StringIO()
    cached = False
    data_dir = None if force else cached_data_dir(problem_id, SAMPLE_PROFILE)
    if data_dir is None:
        with contextlib.redirect_stdout(output):
            data_dir = generate(problem_id, SAMPLE_PROFILE, force)
    else:
        cached = True
        output.write("Using cached sample data.")
    return build_sample_cases_result(data_dir, output.getvalue().strip(), cached)


def generate_problem_events(
    problem_id: str,
    profile: str | None,
    force: bool,
) -> Iterator[str]:
    """Stream test data generation progress as Server-Sent Events."""
    events: queue.Queue[dict[str, Any] | object] = queue.Queue()

    def progress(message: str) -> None:
        events.put({"event": "log", "data": {"message": message}})

    def worker() -> None:
        output = io.StringIO()
        try:
            progress("Starting test data generation.")
            with contextlib.redirect_stdout(output):
                data_dir = generate(problem_id, profile, force, progress=progress)
            events.put(
                {"event": "result", "data": build_generate_result(data_dir, output.getvalue())}
            )
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


def default_filename(problem_id: str, filename: str | None) -> str:
    """Return a safe filename for pasted source code."""
    if filename:
        name = Path(filename).name
    else:
        name = f"main-{problem_id}.py"
    if not name or name in {".", ".."}:
        raise JudgeError("invalid source filename")
    return name


def source_file_for_entry(entry_dir: Path, metadata: dict[str, Any] | None) -> Path | None:
    """Return the source file path for a cached source history directory."""
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
    """Return display metadata for one cached source history entry."""
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


def list_source_history(limit: int = SOURCE_HISTORY_LIMIT) -> dict[str, Any]:
    """Return recently submitted web source files without loading their full contents."""
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
    """Return source code text for one cached source history entry."""
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
            last_run_result = run_result(last_run["runId"])
    return {
        **metadata,
        "lastRunResult": last_run_result,
        "sourceText": source_file.read_text(encoding="utf-8", errors="replace"),
    }


def delete_source_history(source_id: str) -> dict[str, Any]:
    """Delete one cached source history entry."""
    entry_dir = source_entry_dir(source_id)
    if not entry_dir.exists():
        raise JudgeError(f"source history entry not found: {source_id}")
    shutil.rmtree(entry_dir)
    return {"deleted": True, "sourceId": source_id}


def source_path_from_request(
    problem_id: str,
    source_mode: str,
    source_path: str | None,
    source_text: str | None,
    filename: str | None,
) -> Path:
    """Resolve a local source path or persist pasted source text."""
    if source_mode == "path":
        if not source_path:
            raise JudgeError("source path is required")
        path = Path(source_path).expanduser()
        if not path.exists():
            raise JudgeError(f"source file not found: {path}")
        return save_existing_source(path, problem_id, "path")

    if source_mode == "upload":
        if not source_path:
            raise JudgeError("uploaded source path is required")
        path = Path(source_path)
        if not path.exists():
            raise JudgeError(f"uploaded source file not found: {path}")
        with contextlib.suppress(JudgeError):
            return ensure_inside(path, source_history_root())
        return save_existing_source(path, problem_id, "upload")

    if not source_text:
        raise JudgeError("source text is required")
    return save_text_source(source_text, filename, problem_id)


def enrich_run_result(
    result: dict[str, Any],
    run_dir: Path | None = None,
    source: Path | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Add web-facing display fields to a saved run result."""
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
    """Build a web response from a completed run directory."""
    result = enrich_run_result(read_json(run_dir / "result.json"), run_dir, source, message)
    source_id = attach_run_to_source(source, result)
    if source_id is not None:
        result["sourceId"] = source_id
    return result


def format_duration(milliseconds: int) -> str:
    """Format a millisecond duration for web status summaries."""
    if milliseconds < 1000:
        return f"{milliseconds} ms"
    return f"{milliseconds / 1000:.2f} s"


def run_problem(
    problem_id: str,
    profile: str | None,
    source_mode: str,
    source_path: str | None,
    source_text: str | None,
    filename: str | None,
) -> dict[str, Any]:
    """Judge a source path or pasted source text and return run result data."""
    source = source_path_from_request(problem_id, source_mode, source_path, source_text, filename)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        run_dir = run_submission(source, problem_id, HIDDEN_PROFILE)
    return build_run_result(run_dir, source, output.getvalue())


def run_uploaded_problem(
    problem_id: str,
    profile: str | None,
    file_obj: BinaryIO,
    filename: str | None,
) -> dict[str, Any]:
    """Judge an uploaded source file and return run result data."""
    source = save_uploaded_source(file_obj, filename, problem_id)
    return run_problem(problem_id, profile, "upload", str(source), None, None)


def sse(event: str, data: dict[str, Any]) -> str:
    """Format one Server-Sent Events block."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def run_problem_events(
    problem_id: str,
    profile: str | None,
    source: Path,
) -> Iterator[str]:
    """Stream run progress and final result as Server-Sent Events."""
    events: queue.Queue[dict[str, Any] | object] = queue.Queue()

    def progress(message: str) -> None:
        events.put({"event": "log", "data": {"message": message}})

    def worker() -> None:
        output = io.StringIO()
        try:
            progress("Starting judge run.")
            with contextlib.redirect_stdout(output):
                run_dir = run_submission(source, problem_id, HIDDEN_PROFILE, progress=progress)
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
    """Persist the submitted source for a streaming run request."""
    if source_mode == "upload":
        if file_obj is None:
            raise JudgeError("source file upload is required")
        return save_uploaded_source(file_obj, upload_filename, problem_id)
    if source_mode == "text":
        if not source_text:
            raise JudgeError("source text is required")
        return save_text_source(source_text, text_filename, problem_id)
    raise JudgeError(f"unsupported source mode: {source_mode}")


def current_web_config() -> dict[str, Any]:
    """Return web configuration values that the UI should display."""
    return {
        "officialRepository": official_pack_repository(),
        "sampleProfile": SAMPLE_PROFILE,
        "judgeProfile": HIDDEN_PROFILE,
        "webDebug": web_debug_enabled(),
    }


def run_result(run_id: str) -> dict[str, Any]:
    """Return a saved run result JSON object."""
    validate_safe_id("run id", run_id)
    run_dir = cache_root() / "runs" / run_id
    result_path = run_dir / "result.json"
    if not result_path.exists():
        raise JudgeError(f"run result not found: {run_id}")
    return enrich_run_result(read_json(result_path), run_dir)


def preview_artifact_text(text: str, limit: int = ARTIFACT_PREVIEW_LIMIT) -> dict[str, Any]:
    """Return a display-safe artifact preview and truncation metadata."""
    if len(text) <= limit:
        return {"text": text, "truncated": False, "omittedChars": 0}
    omitted = len(text) - limit
    preview = text[:limit].rstrip()
    preview += f"\n\n... truncated after {limit} chars, omitted {omitted} chars ..."
    return {"text": preview, "truncated": True, "omittedChars": omitted}


def wrong_case(run_id: str, case_id: str) -> dict[str, Any]:
    """Return wrong-answer artifacts for one run case."""
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


def cache_status() -> dict[str, Any]:
    """Return cache status data with formatted sizes."""
    data = cache_status_data()
    data["totalSizeLabel"] = format_size(int(data["totalSize"]))
    runs = data["runs"]
    if isinstance(runs, dict):
        runs["sizeLabel"] = format_size(int(runs["size"]))
    sources = data.get("sources")
    if isinstance(sources, dict):
        sources["sizeLabel"] = format_size(int(sources["size"]))
    for problem in data["problems"]:
        problem["sizeLabel"] = format_size(int(problem["size"]))
    return data


def cache_clear(
    problem: str | None,
    profile: str | None,
    runs: bool,
    all_entries: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Preview or apply a cache deletion request."""
    plan = build_cache_clear_plan(problem, profile, runs, all_entries)
    targets = [
        {
            "path": str(target),
            "label": rel(target, plan.root),
        }
        for target in plan.targets
    ]
    if not dry_run:
        delete_cache_targets(plan.targets, plan.operation_root)
    return {
        "dryRun": dry_run,
        "deleted": not dry_run,
        "totalSize": plan.total_size,
        "totalSizeLabel": format_size(plan.total_size),
        "targets": targets,
    }


def dashboard_status() -> dict[str, Any]:
    """Return the initial dashboard status for the web UI."""
    return {
        "problems": list_problems(),
        "packs": list_packs(),
        "cache": cache_status(),
        "config": current_web_config(),
    }
