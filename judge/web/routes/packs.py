"""문제팩 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
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
    """문제팩 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Returns:
        list[dict]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 데이터입니다.
    """
    try:
        return services.list_packs()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/install")
def api_pack_install(http_request: Request, request: PackInstallRequest) -> dict:
    """문제팩 설치 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        http_request (Request): 원격 실행 허용 여부를 판단할 FastAPI 요청 객체입니다.
        request (PackInstallRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 설치 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(http_request, "pack install")
        return services.install_problem_pack(request.archive_path)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/install/jobs")
def api_pack_install_job(http_request: Request, request: PackInstallRequest) -> dict:
    """문제팩 설치 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        http_request (Request): 원격 실행 허용 여부를 판단할 FastAPI 요청 객체입니다.
        request (PackInstallRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 설치 작업 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(http_request, "pack install")
        jobs = jobs_from_request(http_request)

        def operation(cancel_token, progress):
            progress(
                "Installing local problem pack.",
                label="문제 팩 설치",
                failureStage="pack",
                failureStageLabel="문제 팩 설치",
            )
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
    """문제팩 업로드 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        file (Annotated[UploadFile, File()]): 업로드 요청에서 받은 파일 스트림 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 업로드 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(request, "pack upload")
        return services.install_uploaded_problem_pack(file.file, file.filename)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/upload/jobs")
def api_pack_upload_job(request: Request, file: Annotated[UploadFile, File()]) -> dict:
    """문제팩 업로드 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        file (Annotated[UploadFile, File()]): 업로드 요청에서 받은 파일 스트림 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 업로드 작업 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(request, "pack upload")
        uploaded = services.save_uploaded_pack(file.file, file.filename)
        jobs = jobs_from_request(request)

        def operation(cancel_token, progress):
            progress(
                "Installing uploaded problem pack.",
                label="문제 팩 업로드",
                failureStage="pack",
                failureStageLabel="문제 팩 설치",
            )
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
    """문제팩 다운로드 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        http_request (Request): 원격 실행 허용 여부를 판단할 FastAPI 요청 객체입니다.
        request (PackDownloadRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 다운로드 데이터입니다.
    """
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
    """문제팩 다운로드 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        http_request (Request): 원격 실행 허용 여부를 판단할 FastAPI 요청 객체입니다.
        request (PackDownloadRequest): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 다운로드 작업 데이터입니다.
    """
    try:
        ensure_local_web_action_allowed(http_request, "pack download")
        jobs = jobs_from_request(http_request)

        def operation(cancel_token, progress):
            progress(
                "Downloading official problem pack.",
                label="공식 문제 팩 설치",
                failureStage="pack",
                failureStageLabel="문제 팩 설치",
            )
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
