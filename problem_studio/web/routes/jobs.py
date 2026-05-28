"""작업 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from commons.job_queue import ACTIVE_STATUSES
from problem_studio.web.routes.common import (
    job_matches_active_repository,
    jobs_from_request,
    to_http_error,
)
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def api_jobs(request: Request) -> dict:
    """작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 데이터입니다.
    """
    jobs = jobs_from_request(request)
    return {
        "jobs": [
            jobs.job_dict(job)
            for job in jobs.list()
            if job_matches_active_repository(request, job)
        ]
    }


@router.delete("/completed")
def api_jobs_clear_completed(request: Request) -> dict:
    """작업 clear completed 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 clear completed 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "job cleanup")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    return {"cleared": jobs.clear_completed(lambda job: job_matches_active_repository(request, job))}


@router.get("/{job_id}")
def api_job(request: Request, job_id: str) -> dict:
    """작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        job_id (str): 백그라운드 작업 상태와 결과를 조회하는 작업 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 데이터입니다.
    """
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if job is None or not job_matches_active_repository(request, job):
        raise HTTPException(status_code=404, detail="job not found")
    return jobs.job_dict(job)


@router.post("/{job_id}/cancel")
def api_job_cancel(request: Request, job_id: str) -> dict:
    """작업 cancel 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        job_id (str): 백그라운드 작업 상태와 결과를 조회하는 작업 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 cancel 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "job cancel")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if job is None or not job_matches_active_repository(request, job):
        raise HTTPException(status_code=404, detail="job not found")
    if not jobs.cancel(job_id):
        raise HTTPException(status_code=409, detail="job cannot be cancelled")
    return jobs.job_dict(jobs.get(job_id) or job)


@router.delete("/{job_id}")
def api_job_dismiss(request: Request, job_id: str) -> dict:
    """작업 dismiss 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        job_id (str): 백그라운드 작업 상태와 결과를 조회하는 작업 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 dismiss 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "job dismiss")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if job is None or not job_matches_active_repository(request, job):
        raise HTTPException(status_code=404, detail="job not found")
    if job.status in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="active job cannot be dismissed")
    if not jobs.dismiss(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return {"dismissed": True, "jobId": job_id}
