from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import queue
import re
import shutil
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from commons.generate import load_config
from judge.core.artifacts import wrong_artifacts, wrong_diff_text
from judge.core.cache import build_cache_clear_plan, cache_status_data, delete_cache_targets
from judge.core.cases_compile import compile_problem_cases
from judge.core.errors import JudgeError
from judge.core.generation import cache_dir_for, generate
from judge.core.manifest import generation_key, validate_manifest_fast
from judge.core.pack import install_pack, installed_packs
from judge.core.paths import cache_root, current_platform_id, rel, validate_safe_id
from judge.core.problem import discover_problem_ids, load_problem, tool_paths
from judge.core.submission import run_submission
from judge.utils.fs import read_json
from judge.utils.text import format_size

DEFAULT_OFFICIAL_PACK_REPOSITORY = "tony9402/algorithm-modules"
GITHUB_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAMPLE_PROFILE = "sample"
HIDDEN_PROFILE = "hidden"
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
    target = install_pack(Path(archive_path))
    return {"installedPath": str(target), "label": rel(target)}


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


def save_uploaded_source(file_obj: BinaryIO, filename: str | None) -> Path:
    """Persist an uploaded source file and return its path."""
    return save_upload(file_obj, filename, "sources", "main.py")


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


def official_pack_repository(repository: str | None = None) -> str:
    """Return the configured official problem pack repository."""
    repo = repository or os.environ.get("ALJ_OFFICIAL_PACK_REPOSITORY")
    repo = repo or DEFAULT_OFFICIAL_PACK_REPOSITORY
    if not GITHUB_REPOSITORY_RE.match(repo):
        raise JudgeError("official repository must look like owner/name")
    return repo


def github_json(url: str) -> dict[str, Any]:
    """Fetch a GitHub JSON document using the standard library."""
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "algorithm-local-judge",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise JudgeError(f"GitHub request failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise JudgeError(f"GitHub request failed: {exc.reason}") from exc


def select_pack_asset(assets: list[dict[str, Any]], asset_name: str | None) -> dict[str, Any]:
    """Select a .aljpack release asset, preferring the current platform."""
    candidates = [
        asset
        for asset in assets
        if isinstance(asset.get("name"), str) and asset["name"].endswith(".aljpack")
    ]
    if asset_name:
        for asset in candidates:
            if asset["name"] == asset_name:
                return asset
        raise JudgeError(f"official pack asset not found: {asset_name}")
    if not candidates:
        raise JudgeError("official release has no .aljpack assets")
    platform_id = current_platform_id()
    for asset in candidates:
        if platform_id in asset["name"]:
            return asset
    return candidates[0]


def download_asset(url: str, target: Path) -> None:
    """Download one release asset to a local file."""
    request = Request(url, headers={"User-Agent": "algorithm-local-judge"})
    try:
        with urlopen(request, timeout=60) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output)
    except HTTPError as exc:
        raise JudgeError(f"official pack download failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise JudgeError(f"official pack download failed: {exc.reason}") from exc


def download_official_problem_pack(
    repository: str | None = None,
    asset_name: str | None = None,
) -> dict[str, Any]:
    """Download and install a problem pack from the configured public GitHub repo."""
    repo = official_pack_repository(repository)
    release = github_json(f"https://api.github.com/repos/{repo}/releases/latest")
    asset = select_pack_asset(release.get("assets", []), asset_name)
    download_url = asset.get("browser_download_url")
    if not isinstance(download_url, str):
        raise JudgeError(f"official pack asset has no download URL: {asset.get('name')}")
    target_dir = cache_root() / "web-downloads" / "packs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_upload_name(asset.get("name"), "official.aljpack")
    download_asset(download_url, target)
    result = install_problem_pack(str(target))
    result.update(
        {
            "repository": repo,
            "assetName": asset.get("name"),
            "downloadedPath": str(target),
        }
    )
    return result


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
        return path

    if source_mode == "upload":
        if not source_path:
            raise JudgeError("uploaded source path is required")
        path = Path(source_path)
        if not path.exists():
            raise JudgeError(f"uploaded source file not found: {path}")
        return path

    if not source_text:
        raise JudgeError("source text is required")
    validate_safe_id("problem id", problem_id)
    name = default_filename(problem_id, filename)
    target_dir = cache_root() / "web-submissions" / f"{int(time.time() * 1000)}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name
    target.write_text(source_text, encoding="utf-8")
    return target


def build_run_result(run_dir: Path, source: Path, message: str) -> dict[str, Any]:
    """Build a web response from a completed run directory."""
    result = read_json(run_dir / "result.json")
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
    result.update(
        {
            "runDir": str(run_dir),
            "runLabel": rel(run_dir),
            "language": result.get("language") or language_from_filename(source.name),
            "message": message.strip(),
            "firstFailedCase": first_failed["case"] if first_failed else None,
            "metrics": metrics,
        }
    )
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
    source = save_uploaded_source(file_obj, filename)
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
        return save_uploaded_source(file_obj, upload_filename)
    if source_mode == "text":
        if not source_text:
            raise JudgeError("source text is required")
        validate_safe_id("problem id", problem_id)
        name = default_filename(problem_id, text_filename)
        target_dir = cache_root() / "web-submissions" / f"{int(time.time() * 1000)}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / name
        target.write_text(source_text, encoding="utf-8")
        return target
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
    result_path = cache_root() / "runs" / run_id / "result.json"
    if not result_path.exists():
        raise JudgeError(f"run result not found: {run_id}")
    return read_json(result_path)


def wrong_case(run_id: str, case_id: str) -> dict[str, str]:
    """Return wrong-answer artifacts for one run case."""
    data = wrong_artifacts(run_id, case_id)
    data["diff"] = wrong_diff_text(run_id, case_id)
    return data


def cache_status() -> dict[str, Any]:
    """Return cache status data with formatted sizes."""
    data = cache_status_data()
    data["totalSizeLabel"] = format_size(int(data["totalSize"]))
    runs = data["runs"]
    if isinstance(runs, dict):
        runs["sizeLabel"] = format_size(int(runs["size"]))
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
