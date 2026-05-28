from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from commons.job_queue import ACTIVE_STATUSES
from judge.web.routes.common import jobs_from_request, to_http_error
from judge.web.security_policy import ensure_local_web_action_allowed, ensure_remote_run_allowed

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def api_jobs(request: Request) -> dict:
    """Return retained Judge jobs."""
    jobs = jobs_from_request(request)
    return {"jobs": [jobs.job_dict(job) for job in jobs.list()]}


@router.delete("/completed")
def api_jobs_clear_completed(request: Request) -> dict:
    """Dismiss every completed job."""
    try:
        ensure_local_web_action_allowed(request, "job cleanup")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    return {"cleared": jobs.clear_completed()}


@router.get("/{job_id}")
def api_job(request: Request, job_id: str) -> dict:
    """Return one retained Judge job."""
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return jobs.job_dict(job)


@router.post("/{job_id}/cancel")
def api_job_cancel(request: Request, job_id: str) -> dict:
    """Cancel a queued job or request cancellation for a running job."""
    try:
        ensure_remote_run_allowed(request)
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if not jobs.cancel(job_id):
        raise HTTPException(status_code=409, detail="job cannot be cancelled")
    return jobs.job_dict(jobs.get(job_id) or job)


@router.delete("/{job_id}")
def api_job_dismiss(request: Request, job_id: str) -> dict:
    """Dismiss a retained Judge job."""
    try:
        ensure_local_web_action_allowed(request, "job dismiss")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="active job cannot be dismissed")
    if not jobs.dismiss(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return {"dismissed": True, "jobId": job_id}
