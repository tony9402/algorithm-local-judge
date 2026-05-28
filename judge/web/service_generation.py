from __future__ import annotations

import contextlib
import io
import queue
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from judge.core.cases_compile import compile_problem_cases
from judge.core.generation import generate
from judge.core.paths import rel
from judge.utils.fs import read_json
from judge.web.service_common import SSE_DONE, sse


def generate_problem(problem_id: str, profile: str | None, force: bool) -> dict[str, Any]:
    """Generate test data and return a concise result summary."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        data_dir = generate(problem_id, profile, force)
    return build_generate_result(data_dir, output.getvalue())


def generate_problem_with_progress(
    problem_id: str,
    profile: str | None,
    force: bool,
    progress,
) -> dict[str, Any]:
    """Generate test data with a queue progress callback."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        data_dir = generate(problem_id, profile, force, progress=progress)
    return build_generate_result(data_dir, output.getvalue())


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
