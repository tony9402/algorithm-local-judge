"""문제팩 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from commons.job_queue import ACTIVE_STATUSES
from problem_studio.core.packflow import build_problem_pack
from problem_studio.web.routes.common import (
    enqueue_background_job,
    job_matches_active_repository,
    jobs_from_request,
    scoped_lane,
    stream_operation,
    to_http_error,
    workspace_from_request,
)
from problem_studio.web.schemas import PackBuildRequest
from problem_studio.web.security_policy import (
    ensure_local_web_action_allowed,
    ensure_local_write_allowed,
)

router = APIRouter(prefix="/api/problems/{problem_id}/packs", tags=["packs"])
PACK_OUTPUT_DIR = Path("dist/packs")


def pack_job_dict(jobs, job, problem_id: str) -> dict:
    """문제팩 작업 dict 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        jobs (Any): 문제팩 작업 dict을 계산하거나 검증할 때 필요한 작업 입력입니다.
        job (Any): 문제팩 작업 dict을 계산하거나 검증할 때 필요한 작업 입력입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 작업 dict 데이터입니다.
    """
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
    """문제팩 build 스트림 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (PackBuildRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        StreamingResponse: 브라우저가 진행 이벤트를 받을 수 있는 스트리밍 HTTP 응답입니다.
    """
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
    """문제팩 build 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (PackBuildRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 build 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "pack build")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress) -> dict:
            progress(
                f"Building pack {body.pack_id} for problem {problem_id}.",
                label="팩 생성",
                failureStage="pack",
            )
            result = build_problem_pack(
                workspace,
                problem_id,
                body.pack_id,
                PACK_OUTPUT_DIR,
                body.platform_id,
                body.verify_profile,
                cancel_token=cancel_token,
            )
            progress(
                f"Built pack: {result['archiveLabel']}",
                label="팩 생성",
                failureStage="pack",
            )
            return result

        job = enqueue_background_job(
            jobs,
            request=request,
            kind="pack-build",
            title=f"팩 빌드 · {problem_id}",
            problem_id=problem_id,
            lane=scoped_lane(request, problem_id, "pack"),
            target={
                "problemId": problem_id,
                "packId": body.pack_id,
                "verifyProfile": body.verify_profile,
            },
            result_actions={"download": True},
            operation=operation,
        )
        return pack_job_dict(jobs, job, problem_id)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.get("/jobs")
def api_pack_build_jobs(request: Request, problem_id: str) -> dict:
    """문제팩 build 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 build 작업 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(request, "pack job history read")
    except Exception as exc:
        raise to_http_error(exc) from exc
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
    """문제팩 build 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        job_id (str): 백그라운드 작업 상태와 결과를 조회하는 작업 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 build 작업 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(request, "pack job detail read")
    except Exception as exc:
        raise to_http_error(exc) from exc
    jobs = jobs_from_request(request)
    job = jobs.get(job_id)
    if not job or job.problem_id != problem_id or not job_matches_active_repository(request, job):
        raise HTTPException(status_code=404, detail="pack build job not found")
    return pack_job_dict(jobs, job, problem_id)


@router.delete("/jobs/{job_id}")
def api_pack_build_job_dismiss(request: Request, problem_id: str, job_id: str) -> dict:
    """문제팩 build 작업 dismiss 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        job_id (str): 백그라운드 작업 상태와 결과를 조회하는 작업 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 build 작업 dismiss 데이터입니다.
    """
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
    """문제팩 build 작업 cancel 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        job_id (str): 백그라운드 작업 상태와 결과를 조회하는 작업 ID입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 build 작업 cancel 데이터입니다.
    """
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
    """문제팩 build 다운로드 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        job_id (str): 백그라운드 작업 상태와 결과를 조회하는 작업 ID입니다.
    """
    try:
        ensure_local_web_action_allowed(request, "pack artifact download")
    except Exception as exc:
        raise to_http_error(exc) from exc
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
