from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from problem_studio.core.packflow import build_problem_pack
from problem_studio.web.routes.common import (
    jobs_from_request,
    stream_operation,
    workspace_from_request,
)
from problem_studio.web.schemas import PackBuildRequest

router = APIRouter(prefix="/api/problems/{problem_id}/packs", tags=["packs"])
PACK_OUTPUT_DIR = Path("dist/packs")


def pack_job_dict(job, problem_id: str) -> dict:
    """Return a pack job response with a download URL once the artifact is ready."""
    data = job.to_dict()
    if job.status == "succeeded" and isinstance(data.get("result"), dict):
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
    workspace = workspace_from_request(request)

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
    workspace = workspace_from_request(request)
    jobs = jobs_from_request(request)

    def operation() -> dict:
        return build_problem_pack(
            workspace,
            problem_id,
            body.pack_id,
            PACK_OUTPUT_DIR,
            body.platform_id,
            body.verify_profile,
        )

    job = jobs.start(
        kind="pack-build",
        title=f"팩 빌드 · {problem_id}",
        problem_id=problem_id,
        operation=operation,
    )
    return pack_job_dict(job, problem_id)


@router.get("/jobs/{job_id}")
def api_pack_build_job(request: Request, problem_id: str, job_id: str) -> dict:
    """Return the latest state of a background pack build job."""
    job = jobs_from_request(request).get(job_id)
    if not job or job.problem_id != problem_id:
        raise HTTPException(status_code=404, detail="pack build job not found")
    return pack_job_dict(job, problem_id)


@router.get("/jobs/{job_id}/download")
def api_pack_build_download(request: Request, problem_id: str, job_id: str) -> FileResponse:
    """Download a completed pack build artifact."""
    job = jobs_from_request(request).get(job_id)
    if not job or job.problem_id != problem_id:
        raise HTTPException(status_code=404, detail="pack build job not found")
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
