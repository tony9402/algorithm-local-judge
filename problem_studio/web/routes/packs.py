from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from commons.job_queue import ACTIVE_STATUSES
from problem_studio.core.packflow import build_problem_pack
from problem_studio.web.routes.common import (
    jobs_from_request,
    job_matches_active_repository,
    scoped_lane,
    scoped_target,
    stream_operation,
    to_http_error,
    workspace_from_request,
)
from problem_studio.web.schemas import PackBuildRequest
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/problems/{problem_id}/packs", tags=["packs"])
PACK_OUTPUT_DIR = Path("dist/packs")


def pack_job_dict(jobs, job, problem_id: str) -> dict:
    """Return a pack job response with a download URL once the artifact is ready."""
    data = jobs.job_dict(job)
    if data["status"] == "succeeded" and isinstance(data.get("result"), dict):
        data["result"] = {
            **data["result"],
            "downloadUrl": f"/api/problems/{problem_id}/packs/jobs/{job.job_id}/download",
        }
    return data


@router.post("/build/stream")
def api_pack_build_stream(
    request: Request, problem_id: str, body: PackBuildRequest
) -> StreamingResponse:
    """Verify and build a source-free problem pack with progress events."""
    try:
        ensure_local_write_allowed(request, "pack build")
        workspace = workspace_from_request(request)
    except Exception as exc:
        raise to_http_error(exc) from exc

    def operation(progress):
        progress(f"Building pack {body.pack_id} for problem {problem_id}.")
        result = build_problem_pack(
            workspace,
            problem_id,
            body.pack_id,
            PACK_OUTPUT_DIR,
            body.platform_id,
            body.verify_profile,
        )
        progress(f"Built pack: {result['archiveLabel']}")
        return result

    return StreamingResponse(stream_operation(operation), media_type="text/event-stream")


@router.post("/build")
def api_pack_build(request: Request, problem_id: str, body: PackBuildRequest) -> dict:
    """Start a background problem pack build and return the job state."""
    try:
        ensure_local_write_allowed(request, "pack build")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token) -> dict:
            return build_problem_pack(
                workspace,
                problem_id,
                body.pack_id,
                PACK_OUTPUT_DIR,
                body.platform_id,
                body.verify_profile,
                cancel_token=cancel_token,
            )

        job = jobs.start(
            kind="pack-build",
            title=f"팩 빌드 · {problem_id}",
            problem_id=problem_id,
            operation=operation,
            cancel_supported=True,
            app="problem_studio",
            lane=scoped_lane(request, problem_id, "pack"),
            target=scoped_target(
                request,
                {
                    "problemId": problem_id,
                    "packId": body.pack_id,
                    "verifyProfile": body.verify_profile,
                },
            ),
            result_actions={"download": True},
        )
        return pack_job_dict(jobs, job, problem_id)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/jobs")
def api_pack_build_jobs(request: Request, problem_id: str) -> dict:
    """Return retained background pack jobs for one problem."""
    jobs = jobs_from_request(request)
    return {
        "jobs": [
            pack_job_dict(jobs, job, problem_id)
            for job in jobs.list(problem_id)
            if job.problem_id == problem_id and job_matches_active_repository(request, job)
        ]
    }


@router.get("/jobs/{job_id}")
def api_pack_build_job(request: Request, problem_id: str, job_id: str) -> dict:
    """Return the latest state of a background pack build job."""
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if not job or job.problem_id != problem_id or not job_matches_active_repository(request, job):
        raise HTTPException(status_code=404, detail="pack build job not found")
    return pack_job_dict(jobs, job, problem_id)


@router.delete("/jobs/{job_id}")
def api_pack_build_job_dismiss(request: Request, problem_id: str, job_id: str) -> dict:
    """Dismiss a retained background pack build job."""
    try:
        ensure_local_write_allowed(request, "pack build job dismiss")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if not job or job.problem_id != problem_id or not job_matches_active_repository(request, job):
        raise HTTPException(status_code=404, detail="pack build job not found")
    if job.status in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="active pack build job cannot be dismissed")
    if not jobs.dismiss(job_id):
        raise HTTPException(status_code=404, detail="pack build job not found")
    return {"dismissed": True, "jobId": job_id}


@router.post("/jobs/{job_id}/cancel")
def api_pack_build_job_cancel(request: Request, problem_id: str, job_id: str) -> dict:
    """Cancel a running background pack build job."""
    try:
        ensure_local_write_allowed(request, "pack build job cancel")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if not job or job.problem_id != problem_id or not job_matches_active_repository(request, job):
        raise HTTPException(status_code=404, detail="pack build job not found")
    if not jobs.cancel(job_id):
        raise HTTPException(status_code=409, detail="pack build job cannot be cancelled")
    refreshed = jobs.get(job_id)
    return pack_job_dict(jobs, refreshed or job, problem_id)


@router.get("/jobs/{job_id}/download")
def api_pack_build_download(request: Request, problem_id: str, job_id: str) -> FileResponse:
    """Download a completed pack build artifact."""
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if not job or job.problem_id != problem_id or not job_matches_active_repository(request, job):
        raise HTTPException(status_code=404, detail="pack build job not found")
    if jobs.job_dict(job)["status"] == "stale":
        raise HTTPException(status_code=409, detail="pack build job is stale")
    if job.status != "succeeded" or not job.result:
        raise HTTPException(status_code=409, detail="pack build is not complete")
    if problem_id not in job.result.get("problems", []):
        raise HTTPException(status_code=400, detail="pack artifact does not contain this problem")
    archive_path = Path(str(job.result.get("archivePath", ""))).resolve()
    workspace = workspace_from_request(request).resolve()
    try:
        archive_path.relative_to((workspace / PACK_OUTPUT_DIR).resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="pack artifact is outside the output directory",
        ) from exc
    if archive_path.suffix != ".aljpack":
        raise HTTPException(status_code=400, detail="pack artifact has an invalid extension")
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="pack artifact not found")
    return FileResponse(
        archive_path,
        media_type="application/gzip",
        filename=archive_path.name,
    )
