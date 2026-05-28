"""jobs 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
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
    """api_jobs 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
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
    """api_jobs_clear_completed 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    try:
        ensure_local_write_allowed(request, "job cleanup")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    return {"cleared": jobs.clear_completed(lambda job: job_matches_active_repository(request, job))}


@router.get("/{job_id}")
def api_job(request: Request, job_id: str) -> dict:
    """api_job 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        job_id (str): 작업 ID입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if job is None or not job_matches_active_repository(request, job):
        raise HTTPException(status_code=404, detail="job not found")
    return jobs.job_dict(job)


@router.post("/{job_id}/cancel")
def api_job_cancel(request: Request, job_id: str) -> dict:
    """api_job_cancel 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        job_id (str): 작업 ID입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
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
    """api_job_dismiss 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        job_id (str): 작업 ID입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
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
