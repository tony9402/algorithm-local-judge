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
    """Return a workspace bulk build job response."""
    return jobs.job_dict(job)


@router.post("/packs/build-all/stream")
def api_workspace_pack_build_all_stream(
    request: Request,
    body: BulkPackBuildRequest,
) -> StreamingResponse:
    """Full-test selected problems and build one pack containing them."""
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
    """Start a cancellable background full-workspace pack build."""
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
    """Return retained workspace bulk build jobs."""
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
    """Return the latest state of a workspace bulk build job."""
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
    """Cancel a running workspace bulk build job."""
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
    """Dismiss a retained workspace bulk build job."""
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
