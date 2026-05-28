"""service_generation 모듈의 공개 동작을 설명합니다.

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
from typing import Any

from judge.core.cases_compile import compile_problem_cases
from judge.core.generation import generate
from judge.core.paths import rel
from judge.utils.fs import read_json
from judge.web.service_common import SSE_DONE, sse


def generate_problem(problem_id: str, profile: str | None, force: bool) -> dict[str, Any]:
    """generate_problem 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
        force (bool): `force` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
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
    """generate_problem_with_progress 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
        force (bool): `force` 값입니다.
        progress (Any): `progress` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        data_dir = generate(problem_id, profile, force, progress=progress)
    return build_generate_result(data_dir, output.getvalue())


def compile_problem_cases_result(problem_id: str, profile: str | None) -> dict[str, Any]:
    """compile_problem_cases_result 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    return compile_problem_cases(problem_id, profile).to_dict()


def build_generate_result(data_dir: Path, message: str) -> dict[str, Any]:
    """build_generate_result 함수를 실행하고 결과를 반환합니다.
    
    Args:
        data_dir (Path): `data_dir` 값입니다.
        message (str): 메시지입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
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
    """generate_problem_events 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
        force (bool): `force` 값입니다.
    
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
