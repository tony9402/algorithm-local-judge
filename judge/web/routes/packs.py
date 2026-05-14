from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from judge.web import services
from judge.web.routes.common import to_http_error
from judge.web.schemas import PackDownloadRequest, PackInstallRequest

router = APIRouter(prefix="/api/packs", tags=["packs"])


@router.get("")
def api_packs() -> list[dict]:
    """Return installed problem packs."""
    try:
        return services.list_packs()
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/install")
def api_pack_install(request: PackInstallRequest) -> dict:
    """Install a problem pack from a local path."""
    try:
        return services.install_problem_pack(request.archive_path)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/upload")
def api_pack_upload(file: Annotated[UploadFile, File()]) -> dict:
    """Install an uploaded problem pack."""
    try:
        return services.install_uploaded_problem_pack(file.file, file.filename)
    except Exception as exc:
        raise to_http_error(exc) from exc


@router.post("/download")
def api_pack_download(request: PackDownloadRequest) -> dict:
    """Download and install a problem pack from the official GitHub repo."""
    try:
        return services.download_official_problem_pack(request.repository, request.asset_name)
    except Exception as exc:
        raise to_http_error(exc) from exc
