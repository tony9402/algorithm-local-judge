from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile

from judge.web import services
from judge.web.routes.common import enqueue_background_job, jobs_from_request, to_http_error
from judge.web.schemas import PackDownloadRequest, PackInstallRequest
from judge.web.security_policy import ensure_local_web_action_allowed

router = APIRouter(prefix="/api/packs", tags=["packs"])


@router.get("")
def api_packs() -> list[dict]:
    """Return installed problem packs."""
    try:
        return services.list_packs()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/install")
def api_pack_install(http_request: Request, request: PackInstallRequest) -> dict:
    """Install a problem pack from a local path."""
    try:
        ensure_local_web_action_allowed(http_request, "pack install")
        return services.install_problem_pack(request.archive_path)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/install/jobs")
def api_pack_install_job(http_request: Request, request: PackInstallRequest) -> dict:
    """Queue local problem pack installation."""
    try:
        ensure_local_web_action_allowed(http_request, "pack install")
        jobs = jobs_from_request(http_request)

        def operation(cancel_token, progress):
            progress("Installing local problem pack.", label="Pack install")
            cancel_token.check()
            result = services.install_problem_pack(request.archive_path)
            cancel_token.check()
            return result

        job = enqueue_background_job(
            jobs,
            kind="judge-pack-install",
            title="Install Pack",
            problem_id="__packs__",
            lane="judge:packs:install",
            target={"archivePath": request.archive_path},
            operation=operation,
            result_actions={"refresh": True},
            cancel_supported=False,
            cancel_mode="blocked",
            cancel_blocked_reason="설치 commit 단계에서는 취소가 다음 안전 지점에서 반영됩니다.",
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/upload")
def api_pack_upload(request: Request, file: Annotated[UploadFile, File()]) -> dict:
    """Install an uploaded problem pack."""
    try:
        ensure_local_web_action_allowed(request, "pack upload")
        return services.install_uploaded_problem_pack(file.file, file.filename)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/upload/jobs")
def api_pack_upload_job(request: Request, file: Annotated[UploadFile, File()]) -> dict:
    """Queue uploaded problem pack installation."""
    try:
        ensure_local_web_action_allowed(request, "pack upload")
        uploaded = services.save_uploaded_pack(file.file, file.filename)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
            progress("Installing uploaded problem pack.", label="Pack upload")
            cancel_token.check()
            result = services.install_problem_pack(str(uploaded))
            result["uploadedPath"] = str(uploaded)
            cancel_token.check()
            return result

        job = enqueue_background_job(
            jobs,
            kind="judge-pack-upload",
            title="Install Uploaded Pack",
            problem_id="__packs__",
            lane="judge:packs:install",
            target={"filename": uploaded.name, "uploadedPath": str(uploaded)},
            operation=operation,
            result_actions={"refresh": True},
            input_snapshot_summary=uploaded.name,
            cancel_supported=False,
            cancel_mode="blocked",
            cancel_blocked_reason=(
                "압축 해제와 설치 commit 단계에서는 취소가 다음 안전 지점에서 반영됩니다."
            ),
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/download")
def api_pack_download(http_request: Request, request: PackDownloadRequest) -> dict:
    """Download and install a problem pack from the official GitHub repo."""
    try:
        ensure_local_web_action_allowed(http_request, "pack download")
        return services.download_official_problem_pack(
            request.repository,
            request.asset_name,
            request.ref,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/download/jobs")
def api_pack_download_job(http_request: Request, request: PackDownloadRequest) -> dict:
    """Queue official problem pack download and installation."""
    try:
        ensure_local_web_action_allowed(http_request, "pack download")
        jobs = jobs_from_request(http_request)

        def operation(cancel_token, progress):
            progress("Downloading official problem pack.", label="Official pack install")
            cancel_token.check()
            result = services.download_official_problem_pack(
                request.repository,
                request.asset_name,
                request.ref,
            )
            cancel_token.check()
            return result

        job = enqueue_background_job(
            jobs,
            kind="judge-pack-download",
            title="Install Official Problems",
            problem_id="__packs__",
            lane="judge:packs:install",
            target={
                "repository": request.repository,
                "assetName": request.asset_name,
                "ref": request.ref,
            },
            operation=operation,
            result_actions={"refresh": True},
            cancel_supported=False,
            cancel_mode="blocked",
            cancel_blocked_reason=(
                "다운로드 후 검증/설치 단계에서는 취소가 다음 안전 지점에서 반영됩니다."
            ),
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc
