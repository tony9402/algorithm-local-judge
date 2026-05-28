"""서비스 생성 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
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
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        data_dir = generate(problem_id, profile, force, progress=progress)
    return build_generate_result(data_dir, output.getvalue())


def compile_problem_cases_result(problem_id: str, profile: str | None) -> dict[str, Any]:
    """문제 케이스 결과 소스와 설정을 실행 가능한 산출물과 진단 정보로 변환합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 케이스 결과 데이터입니다.
    """
    return compile_problem_cases(problem_id, profile).to_dict()


def build_generate_result(data_dir: Path, message: str) -> dict[str, Any]:
    """generate 결과에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Args:
        data_dir (Path): 데이터 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        message (str): 사용자에게 표시하거나 커밋/진행 상태에 기록할 메시지입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 generate 결과 데이터입니다.
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
