from __future__ import annotations

import contextlib
import copy
import io
import threading
from pathlib import Path
from typing import Any

from judge.core.generation import cache_dir_for, generate
from judge.core.manifest import generation_key, validate_manifest_fast
from judge.core.paths import rel
from judge.utils.fs import read_json
from judge.web.service_common import SAMPLE_PROFILE

SAMPLE_RESPONSE_CACHE: dict[str, dict[str, Any]] = {}
SAMPLE_RESPONSE_CACHE_LOCK = threading.Lock()


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
