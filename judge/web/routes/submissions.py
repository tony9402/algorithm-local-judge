"""HTTP API for durable Judge submission history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from judge.web.routes.common import to_http_error
from judge.web.security_policy import ensure_local_web_action_allowed
from judge.web.submission_store import ActiveSubmissionError

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


@router.get("")
def api_submissions(
    request: Request,
    problem_id: str | None = Query(default=None),
    status: str | None = Query(
        default=None,
        pattern=(
            "^(queued|running|completed|cancelled|interrupted|accepted|wrong_answer|"
            "compile_error|runtime_error|time_limit|memory_limit|system_error)$"
        ),
    ),
    language: str | None = Query(default=None),
    profile: str | None = Query(default=None),
    query: str | None = Query(default=None),
    order: str = Query(default="newest", pattern="^(newest|oldest)$"),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        ensure_local_web_action_allowed(request, "submission history read")
        return request.app.state.submissions.list(
            problem_id=problem_id,
            status=status,
            language=language,
            profile=profile,
            query=query,
            order=order,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        if isinstance(exc, ActiveSubmissionError):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise to_http_error(exc) from exc


@router.delete("")
def api_submissions_clear(
    request: Request,
    confirm: bool = Query(default=False),
) -> dict:
    try:
        ensure_local_web_action_allowed(request, "submission history clear")
        if not confirm:
            raise HTTPException(status_code=400, detail="confirm=true is required")
        return request.app.state.submissions.clear()
    except Exception as exc:
        if isinstance(exc, ActiveSubmissionError):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise to_http_error(exc) from exc


@router.get("/{submission_id}")
def api_submission(request: Request, submission_id: str) -> dict:
    try:
        ensure_local_web_action_allowed(request, "submission history detail")
        return request.app.state.submissions.detail(submission_id)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/{submission_id}/source", response_class=PlainTextResponse)
def api_submission_source(request: Request, submission_id: str) -> PlainTextResponse:
    try:
        ensure_local_web_action_allowed(request, "submission source detail")
        detail = request.app.state.submissions.detail(submission_id)
        return PlainTextResponse(
            str(detail["sourceText"]),
            headers={"Cache-Control": "no-store"},
        )
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.delete("/{submission_id}")
def api_submission_delete(request: Request, submission_id: str) -> dict:
    try:
        ensure_local_web_action_allowed(request, "submission history delete")
        return request.app.state.submissions.delete(submission_id)
    except Exception as exc:
        if isinstance(exc, ActiveSubmissionError):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise to_http_error(exc) from exc
