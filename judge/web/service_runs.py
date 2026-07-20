"""서비스 실행 웹 백엔드 구성과 응답 데이터 조립을 담당합니다."""

from __future__ import annotations

import contextlib
import io
import queue
import threading
from collections.abc import Callable, Iterator
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
    source_language_id,
    source_path_from_request,
)

RUN_STATUS_LABELS = {
    "accepted": "맞았습니다",
    "wrong_answer": "오답",
    "compile_error": "컴파일 오류",
    "runtime_error": "런타임 오류",
    "time_limit": "시간 초과",
    "memory_limit": "메모리 초과",
}


def run_status_label(status: str | None) -> str:
    return RUN_STATUS_LABELS.get(status or "", status or "알 수 없는 결과")


def run_failure_stage(status: str | None) -> str:
    if status == "compile_error":
        return "tools"
    return "solutions"


def run_failure_details(
    result: dict[str, Any],
    first_failed: dict[str, Any] | None,
    run_dir: Path | None,
    source: Path | None,
) -> list[dict[str, Any]]:
    status = str(result.get("status") or "")
    label = run_status_label(status)
    message = str(result.get("message") or "").strip()
    detail: dict[str, Any] = {
        "type": status or "judge-run",
        "status": status,
        "label": label,
        "message": message or f"채점 결과가 {label}입니다.",
    }
    if first_failed:
        case_id = first_failed.get("case")
        detail["case"] = case_id
        detail["target"] = f"case {case_id}" if case_id else "실패 케이스"
        detail["message"] = str(first_failed.get("message") or detail["message"])
    elif result.get("compileLog"):
        detail["target"] = result.get("compileLog")
    elif source is not None:
        detail["target"] = source.name
    if run_dir is not None:
        detail["runDir"] = str(run_dir)
    for key in ("problemId", "profile", "language", "runId"):
        value = result.get(key)
        if value:
            detail[key] = value
    return [detail]


def enrich_run_result(
    result: dict[str, Any],
    run_dir: Path | None = None,
    source: Path | None = None,
    message: str | None = None,
) -> dict[str, Any]:
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
    status = result.get("status")
    result["passed"] = status == "accepted"
    result["statusLabel"] = run_status_label(status)
    if status and status != "accepted":
        result["errorKind"] = "judge-verdict"
        result["failureStage"] = run_failure_stage(status)
        result["failureStageLabel"] = "채점 결과"
        result["failureDetails"] = run_failure_details(result, first_failed, run_dir, source)
    return result


def build_run_result(run_dir: Path, source: Path, message: str) -> dict[str, Any]:
    """실행 결과에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Args:
        run_dir (Path): 실행 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        source (Path): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
        message (str): 사용자에게 표시하거나 커밋/진행 상태에 기록할 메시지입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 실행 결과 데이터입니다.
    """
    result = enrich_run_result(read_json(run_dir / "result.json"), run_dir, source, message)
    source_id = attach_run_to_source(source, result)
    if source_id is not None:
        result["sourceId"] = source_id
    return result


def language_for_source(source: Path, fallback: str | None = None) -> str | None:
    return fallback or source_language_id(source)


def resolve_run_profile(profile: str | None) -> str:
    """실행 프로필 식별자나 상대 경로를 실제 사용할 수 있는 대상으로 확정합니다.

    Args:
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 실행 프로필 문자열입니다.
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
    language: str | None = None,
) -> dict[str, Any]:
    """문제 실행에 필요한 입력을 준비하고 외부 프로세스나 서비스 호출을 수행합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        source_mode (str): 소스가 경로, 업로드, 직접 입력 중 어떤 방식으로 전달됐는지 나타냅니다.
        source_path (str | None): 로컬에서 실행할 제출 소스 파일 경로입니다.
        source_text (str | None): 요청 본문으로 전달된 제출 소스 코드입니다.
        filename (str | None): 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 데이터입니다.
    """
    source = source_path_from_request(
        problem_id, source_mode, source_path, source_text, filename, language
    )
    run_profile = resolve_run_profile(profile)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        run_dir = run_submission(
            source,
            problem_id,
            run_profile,
            stop_on_first_failure=False,
            language=language_for_source(source, language),
        )
    return build_run_result(run_dir, source, output.getvalue())


def run_problem_source_with_progress(
    problem_id: str,
    profile: str | None,
    source: Path,
    progress,
    language: str | None = None,
) -> dict[str, Any]:
    """문제 소스 진행 상태 실행에 필요한 입력을 준비하고 외부 프로세스나 서비스 호출을 수행합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        source (Path): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
        progress (Any): 장시간 작업의 단계와 메시지를 UI 작업 상태로 전달하는 콜백입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 소스 진행 상태 데이터입니다.
    """
    run_profile = resolve_run_profile(profile)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        run_dir = run_submission(
            source,
            problem_id,
            run_profile,
            progress=progress,
            stop_on_first_failure=False,
            language=language_for_source(source, language),
        )
    return build_run_result(run_dir, source, output.getvalue())


def run_problem_source(
    problem_id: str,
    profile: str | None,
    source: Path,
    language: str | None = None,
) -> dict[str, Any]:
    return run_problem_source_with_progress(problem_id, profile, source, None, language)


def run_uploaded_problem(
    problem_id: str,
    profile: str | None,
    file_obj: BinaryIO,
    filename: str | None,
    language: str | None = None,
) -> dict[str, Any]:
    """uploaded 문제 실행에 필요한 입력을 준비하고 외부 프로세스나 서비스 호출을 수행합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        file_obj (BinaryIO): uploaded 문제을 계산하거나 검증할 때 필요한 파일 obj 입력입니다.
        filename (str | None): 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 uploaded 문제 데이터입니다.
    """
    source = save_uploaded_source(file_obj, filename, problem_id, language)
    return run_problem_source(problem_id, profile, source, language)


def run_problem_events(
    problem_id: str,
    profile: str | None,
    source: Path,
    language: str | None = None,
    on_started: Callable[[], None] | None = None,
    on_result: Callable[[dict[str, Any]], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> Iterator[str]:
    """문제 events 실행에 필요한 입력을 준비하고 외부 프로세스나 서비스 호출을 수행합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        source (Path): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.

    Returns:
        Iterator[str]: 클라이언트에 순서대로 전달할 SSE 이벤트 문자열 반복자입니다.
    """
    events: queue.Queue[dict[str, Any] | object] = queue.Queue()

    def progress(message: str) -> None:
        events.put({"event": "log", "data": {"message": message}})

    def worker() -> None:
        output = io.StringIO()
        try:
            if on_started is not None:
                on_started()
            run_profile = resolve_run_profile(profile)
            progress("Starting judge run.")
            with contextlib.redirect_stdout(output):
                run_dir = run_submission(
                    source,
                    problem_id,
                    run_profile,
                    progress=progress,
                    stop_on_first_failure=False,
                    language=language_for_source(source, language),
                )
            result = build_run_result(run_dir, source, output.getvalue())
            if on_result is not None:
                on_result(result)
            events.put({"event": "result", "data": result})
        except Exception as exc:
            if on_error is not None:
                on_error(exc)
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
    language: str | None = None,
) -> Path:
    """소스 스트림 데이터를 다음 요청에서도 사용할 수 있도록 안전한 위치에 저장합니다.

    Args:
        source_mode (str): 소스가 경로, 업로드, 직접 입력 중 어떤 방식으로 전달됐는지 나타냅니다.
        file_obj (BinaryIO | None): 소스 스트림을 계산하거나 검증할 때 필요한 파일 obj 입력입니다.
        upload_filename (str | None): 소스 스트림을 계산하거나 검증할 때 필요한 업로드 filename 입력입니다.
        source_text (str | None): 요청 본문으로 전달된 제출 소스 코드입니다.
        text_filename (str | None): 소스 스트림을 계산하거나 검증할 때 필요한 텍스트 filename 입력입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.

    Returns:
        Path: 검증된 소스 스트림 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    if source_mode == "upload":
        if file_obj is None:
            raise JudgeError("source file upload is required")
        return save_uploaded_source(file_obj, upload_filename, problem_id, language)
    if source_mode == "text":
        if not source_text:
            raise JudgeError("source text is required")
        return save_text_source(source_text, text_filename, problem_id, language)
    raise JudgeError(f"unsupported source mode: {source_mode}")


def run_result(run_id: str) -> dict[str, Any]:
    """결과 실행에 필요한 입력을 준비하고 외부 프로세스나 서비스 호출을 수행합니다.

    Args:
        run_id (str): 저장된 실행 결과와 산출물 디렉터리를 찾는 실행 ID입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 결과 데이터입니다.
    """
    validate_safe_id("run id", run_id)
    run_dir = cache_root() / "runs" / run_id
    result_path = run_dir / "result.json"
    if not result_path.exists():
        raise JudgeError(f"run result not found: {run_id}")
    return enrich_run_result(read_json(result_path), run_dir)


def preview_artifact_text(text: str, limit: int = ARTIFACT_PREVIEW_LIMIT) -> dict[str, Any]:
    if len(text) <= limit:
        return {"text": text, "truncated": False, "omittedChars": 0}
    omitted = len(text) - limit
    preview = text[:limit].rstrip()
    preview += f"\n\n... truncated after {limit} chars, omitted {omitted} chars ..."
    return {"text": preview, "truncated": True, "omittedChars": omitted}


def wrong_case(run_id: str, case_id: str) -> dict[str, Any]:
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
