"""실행 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from commons.job_queue import JobCancelledError
from judge.core.errors import SubmissionCompileError
from judge.web import services
from judge.web.routes.common import (
    enqueue_background_job,
    jobs_from_request,
    record_submission_or_429,
    to_http_error,
)
from judge.web.schemas import RunRequest
from judge.web.security_policy import ensure_local_web_action_allowed, ensure_remote_run_allowed

router = APIRouter(prefix="/api", tags=["runs"])


def _create_submission(request: Request, source, *, problem_id, profile, language, source_mode):
    return request.app.state.submissions.create(
        source,
        problem_id=problem_id,
        profile=profile,
        language=language,
        source_mode=source_mode,
    )


def _record_failure(request: Request, submission_id: str | None, exc: Exception) -> None:
    if submission_id is None:
        return
    try:
        if isinstance(exc, JobCancelledError):
            request.app.state.submissions.cancel(submission_id)
        elif isinstance(exc, SubmissionCompileError):
            request.app.state.submissions.fail(
                submission_id,
                exc,
                verdict="compile_error",
                result=exc.result,
            )
        else:
            request.app.state.submissions.fail(submission_id, exc)
    except Exception:
        pass


def _attach_legacy_source(source, result: dict) -> None:
    source_id = services.attach_run_to_source(source, result)
    if source_id is not None:
        result["sourceId"] = source_id


@router.post("/run")
def api_run(http_request: Request, request: RunRequest) -> dict:
    """데이터 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        http_request (Request): 원격 실행 허용 여부를 판단할 FastAPI 요청 객체입니다.
        request (RunRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 데이터 데이터입니다.
    """
    submission_id = None
    try:
        ensure_remote_run_allowed(http_request)
        source = services.source_path_from_request(
            request.problem_id,
            request.source_mode,
            request.source_path,
            request.source_text,
            request.filename,
            request.language,
        )
        record_submission_or_429(http_request, request.problem_id)
        submission = _create_submission(
            http_request,
            source,
            problem_id=request.problem_id,
            profile=request.profile,
            language=request.language,
            source_mode=request.source_mode,
        )
        submission_id = submission["submissionId"]
        submission_source = http_request.app.state.submissions.source_path(submission_id)
        http_request.app.state.submissions.mark_running(submission_id)
        result = services.run_problem_source(
            request.problem_id,
            request.profile,
            submission_source,
            request.language,
        )
        _attach_legacy_source(source, result)
        result["submissionId"] = submission_id
        http_request.app.state.submissions.complete(submission_id, result)
        return result
    except Exception as exc:
        _record_failure(http_request, submission_id, exc)
        raise to_http_error(exc) from exc


@router.post("/run/upload")
def api_run_upload(
    request: Request,
    problem_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    profile: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
) -> dict:
    """업로드 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (Annotated[str, Form()]): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        file (Annotated[UploadFile, File()]): 업로드 요청에서 받은 파일 스트림 객체입니다.
        profile (Annotated[str | None, Form()]): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 업로드 데이터입니다.
    """
    submission_id = None
    try:
        ensure_remote_run_allowed(request)
        source = services.save_uploaded_source(file.file, file.filename, problem_id, language)
        record_submission_or_429(request, problem_id)
        submission = _create_submission(
            request,
            source,
            problem_id=problem_id,
            profile=profile,
            language=language,
            source_mode="upload",
        )
        submission_id = submission["submissionId"]
        submission_source = request.app.state.submissions.source_path(submission_id)
        request.app.state.submissions.mark_running(submission_id)
        result = services.run_problem_source(
            problem_id, profile or None, submission_source, language
        )
        _attach_legacy_source(source, result)
        result["submissionId"] = submission_id
        request.app.state.submissions.complete(submission_id, result)
        return result
    except Exception as exc:
        _record_failure(request, submission_id, exc)
        raise to_http_error(exc) from exc


@router.post("/run/stream")
def api_run_stream(
    request: Request,
    problem_id: Annotated[str, Form()],
    source_mode: Annotated[str, Form()],
    profile: Annotated[str | None, Form()] = None,
    filename: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    source_text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> StreamingResponse:
    """스트림 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (Annotated[str, Form()]): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        source_mode (Annotated[str, Form()]): 소스가 경로, 업로드, 직접 입력 중 어떤 방식으로 전달됐는지 나타냅니다.
        profile (Annotated[str | None, Form()]): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        filename (Annotated[str | None, Form()]): 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.
        source_text (Annotated[str | None, Form()]): 요청 본문으로 전달된 제출 소스 코드입니다.
        file (Annotated[UploadFile | None, File()]): 업로드 요청에서 받은 파일 스트림 객체입니다.

    Returns:
        StreamingResponse: 브라우저가 진행 이벤트를 받을 수 있는 스트리밍 HTTP 응답입니다.
    """
    try:
        ensure_remote_run_allowed(request)
        source = services.save_source_for_stream(
            source_mode,
            file.file if file is not None else None,
            file.filename if file is not None else None,
            source_text,
            filename,
            problem_id,
            language,
        )
        record_submission_or_429(request, problem_id)
        submission = _create_submission(
            request,
            source,
            problem_id=problem_id,
            profile=profile,
            language=language,
            source_mode=source_mode,
        )
        submission_id = submission["submissionId"]
        submission_source = request.app.state.submissions.source_path(submission_id)

        def on_result(result: dict) -> None:
            _attach_legacy_source(source, result)
            result["submissionId"] = submission_id
            request.app.state.submissions.complete(submission_id, result)

        return StreamingResponse(
            services.run_problem_events(
                problem_id,
                profile or None,
                submission_source,
                language,
                on_started=lambda: request.app.state.submissions.mark_running(submission_id),
                on_result=on_result,
                on_error=lambda exc: _record_failure(request, submission_id, exc),
            ),
            media_type="text/event-stream",
            headers={"X-Submission-Id": submission_id},
        )
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/run/jobs")
def api_run_job(
    request: Request,
    problem_id: Annotated[str, Form()],
    source_mode: Annotated[str, Form()],
    profile: Annotated[str | None, Form()] = None,
    filename: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    source_text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> dict:
    """작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (Annotated[str, Form()]): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        source_mode (Annotated[str, Form()]): 소스가 경로, 업로드, 직접 입력 중 어떤 방식으로 전달됐는지 나타냅니다.
        profile (Annotated[str | None, Form()]): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        filename (Annotated[str | None, Form()]): 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.
        source_text (Annotated[str | None, Form()]): 요청 본문으로 전달된 제출 소스 코드입니다.
        file (Annotated[UploadFile | None, File()]): 업로드 요청에서 받은 파일 스트림 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 데이터입니다.
    """
    submission_id = None
    try:
        ensure_remote_run_allowed(request)
        source = services.save_source_for_stream(
            source_mode,
            file.file if file is not None else None,
            file.filename if file is not None else None,
            source_text,
            filename,
            problem_id,
            language,
        )
        record_submission_or_429(request, problem_id)
        jobs = jobs_from_request(request)
        submission = _create_submission(
            request,
            source,
            problem_id=problem_id,
            profile=profile,
            language=language,
            source_mode=source_mode,
        )
        submission_id = submission["submissionId"]
        submission_source = request.app.state.submissions.source_path(submission_id)

        def operation(cancel_token, progress):
            try:
                request.app.state.submissions.mark_running(submission_id)
                progress(
                    "Starting judge run.",
                    label="채점",
                    failureStage="solutions",
                    failureStageLabel="채점",
                )
                result = services.run_problem_source_with_progress(
                    problem_id,
                    profile or None,
                    submission_source,
                    progress,
                    language,
                )
                cancel_token.check()
                _attach_legacy_source(source, result)
                result["submissionId"] = submission_id
                return result
            except SubmissionCompileError as exc:
                _record_failure(request, submission_id, exc)
                raise

        def terminal(job) -> None:
            try:
                if job.status == "succeeded" and isinstance(job.result, dict):
                    request.app.state.submissions.complete(submission_id, job.result)
                elif job.status == "cancelled":
                    request.app.state.submissions.cancel(submission_id)
                else:
                    error = job.error or "judge job failed"
                    request.app.state.submissions.fail(submission_id, error)
            except Exception:
                pass

        job = enqueue_background_job(
            jobs,
            kind="judge-run",
            title=f"채점 · {problem_id}",
            problem_id=problem_id,
            lane=f"judge:{problem_id}:run",
            target={
                "problemId": problem_id,
                "profile": profile,
                "source": source.name,
                "sourceMode": source_mode,
                "language": language,
                "submissionId": submission_id,
            },
            operation=operation,
            result_actions={"apply": True},
            input_snapshot_summary=source.name,
            terminal_callback=terminal,
        )
        request.app.state.submissions.bind_job(submission_id, job.job_id)
        return jobs.job_dict(job)
    except Exception as exc:
        _record_failure(request, submission_id, exc)
        raise to_http_error(exc) from exc


@router.get("/runs/{run_id}")
def api_run_result(request: Request, run_id: str) -> dict:
    """결과 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        run_id (str): 저장된 실행 결과와 산출물 디렉터리를 찾는 실행 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 결과 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(request, "run result read")
        return services.run_result(run_id)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/runs/{run_id}/wrong/{case_id}")
def api_wrong_case(request: Request, run_id: str, case_id: str) -> dict:
    """오답 케이스 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        run_id (str): 저장된 실행 결과와 산출물 디렉터리를 찾는 실행 ID입니다.
        case_id (str): 입력, 출력, 오답 산출물을 구분하는 케이스 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 오답 케이스 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(request, "wrong case read")
        return services.wrong_case(run_id, case_id)
    except Exception as exc:
        raise to_http_error(exc) from exc
