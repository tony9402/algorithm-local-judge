"""일괄 작업 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from commons.job_queue import ACTIVE_STATUSES
from problem_studio.core.bulk import build_all_problem_packs
from problem_studio.web.routes.common import (
    enqueue_background_job,
    jobs_from_request,
    job_matches_active_repository,
    scoped_lane,
    stream_operation,
    to_http_error,
    workspace_from_request,
)
from problem_studio.web.schemas import BulkPackBuildRequest
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/workspace", tags=["workspace"])
PACK_OUTPUT_DIR = Path("dist/packs")
WORKSPACE_JOB_PROBLEM_ID = "__workspace__"


def bulk_job_dict(jobs, job) -> dict:
    """일괄 작업 작업 dict 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        jobs (Any): 일괄 작업 작업 dict을 계산하거나 검증할 때 필요한 작업 입력입니다.
        job (Any): 일괄 작업 작업 dict을 계산하거나 검증할 때 필요한 작업 입력입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 일괄 작업 작업 dict 데이터입니다.
    """
    return jobs.job_dict(job)


@router.post("/packs/build-all/stream")
def api_workspace_pack_build_all_stream(
    request: Request,
    body: BulkPackBuildRequest,
) -> StreamingResponse:
    """작업 공간 문제팩 build all 스트림 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        body (BulkPackBuildRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        StreamingResponse: 브라우저가 진행 이벤트를 받을 수 있는 스트리밍 HTTP 응답입니다.
    """
    try:
        ensure_local_write_allowed(request, "workspace pack build")
        workspace = workspace_from_request(request)
    except Exception as exc:
        raise to_http_error(exc) from exc

    def operation(progress):
        progress("Starting full workspace test and pack build.")
        result = build_all_problem_packs(
            workspace,
            body.pack_id,
            PACK_OUTPUT_DIR,
            body.platform_id,
            body.verify_profile,
            body.force,
            progress,
            body.max_workers,
            body.problem_ids,
        )
        progress(result["summary"])
        return result

    return StreamingResponse(stream_operation(operation), media_type="text/event-stream")


@router.post("/packs/build-all")
def api_workspace_pack_build_all(request: Request, body: BulkPackBuildRequest) -> dict:
    """작업 공간 문제팩 build all 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        body (BulkPackBuildRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 공간 문제팩 build all 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "workspace pack build")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
            return build_all_problem_packs(
                workspace,
                body.pack_id,
                PACK_OUTPUT_DIR,
                body.platform_id,
                body.verify_profile,
                body.force,
                progress,
                body.max_workers,
                body.problem_ids,
                cancel_token=cancel_token,
            )

        job = enqueue_background_job(
            jobs,
            request=request,
            kind="workspace-pack-build",
            title="전체 문제 테스트/팩 빌드",
            problem_id=WORKSPACE_JOB_PROBLEM_ID,
            lane=scoped_lane(request, "workspace", "pack"),
            target={
                "problemIds": body.problem_ids,
                "packId": body.pack_id,
                "verifyProfile": body.verify_profile,
            },
            result_actions={"download": False},
            operation=operation,
        )
        return bulk_job_dict(jobs, job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/packs/jobs")
def api_workspace_pack_build_jobs(request: Request) -> dict:
    """작업 공간 문제팩 build 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 공간 문제팩 build 작업 데이터입니다.
    """
    jobs = jobs_from_request(request)
    return {
        "jobs": [
            bulk_job_dict(jobs, job)
            for job in jobs.list(WORKSPACE_JOB_PROBLEM_ID)
            if job.problem_id == WORKSPACE_JOB_PROBLEM_ID
            and job_matches_active_repository(request, job)
        ]
    }


@router.get("/packs/jobs/{job_id}")
def api_workspace_pack_build_job(request: Request, job_id: str) -> dict:
    """작업 공간 문제팩 build 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        job_id (str): 백그라운드 작업 상태와 결과를 조회하는 작업 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 공간 문제팩 build 작업 데이터입니다.
    """
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if (
        not job
        or job.problem_id != WORKSPACE_JOB_PROBLEM_ID
        or not job_matches_active_repository(request, job)
    ):
        raise HTTPException(status_code=404, detail="workspace pack build job not found")
    return bulk_job_dict(jobs, job)


@router.post("/packs/jobs/{job_id}/cancel")
def api_workspace_pack_build_job_cancel(request: Request, job_id: str) -> dict:
    """작업 공간 문제팩 build 작업 cancel 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        job_id (str): 백그라운드 작업 상태와 결과를 조회하는 작업 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 공간 문제팩 build 작업 cancel 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "workspace pack build job cancel")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if (
        not job
        or job.problem_id != WORKSPACE_JOB_PROBLEM_ID
        or not job_matches_active_repository(request, job)
    ):
        raise HTTPException(status_code=404, detail="workspace pack build job not found")
    if not jobs.cancel(job_id):
        raise HTTPException(status_code=409, detail="workspace pack build job cannot be cancelled")
    refreshed = jobs.get(job_id)
    return bulk_job_dict(jobs, refreshed or job)


@router.delete("/packs/jobs/{job_id}")
def api_workspace_pack_build_job_dismiss(request: Request, job_id: str) -> dict:
    """작업 공간 문제팩 build 작업 dismiss 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        job_id (str): 백그라운드 작업 상태와 결과를 조회하는 작업 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 공간 문제팩 build 작업 dismiss 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "workspace pack build job dismiss")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if (
        not job
        or job.problem_id != WORKSPACE_JOB_PROBLEM_ID
        or not job_matches_active_repository(request, job)
    ):
        raise HTTPException(status_code=404, detail="workspace pack build job not found")
    if job.status in ACTIVE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="active workspace pack build job cannot be dismissed",
        )
    if not jobs.dismiss(job_id):
        raise HTTPException(status_code=404, detail="workspace pack build job not found")
    return {"dismissed": True, "jobId": job_id}
