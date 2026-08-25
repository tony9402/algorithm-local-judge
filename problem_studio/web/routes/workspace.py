"""작업 공간 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다."""

from __future__ import annotations

from fastapi import APIRouter, Request

from alj_core.errors import JudgeError
from commons.job_queue import ACTIVE_STATUSES
from problem_studio.core.workspace import (
    link_testlib,
    remove_generated_problem_packs,
    resolve_workspace,
)
from problem_studio.web.routes.common import (
    job_matches_active_repository,
    jobs_from_request,
    route_result,
    workspace_from_request,
    workspace_status_from_request,
)
from problem_studio.web.schemas import GeneratedPackRemoveRequest, WorkspaceOpenRequest
from problem_studio.web.security_policy import (
    ensure_local_web_action_allowed,
    ensure_local_write_allowed,
)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("")
def api_workspace(request: Request) -> dict:
    """작업 공간 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 공간 데이터입니다.
    """
    return route_result(
        lambda: (
            ensure_local_web_action_allowed(request, "workspace status read")
            or workspace_status_from_request(request)
        )
    )


@router.post("/open")
def api_workspace_open(request: Request, body: WorkspaceOpenRequest) -> dict:
    """작업 공간 open 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        body (WorkspaceOpenRequest): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 작업 공간 open 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "workspace switching")
        request.app.state.workspace_root = resolve_workspace(body.path)
        request.app.state.active_repository = None
        request.app.state.workspace = request.app.state.workspace_root
        return workspace_status_from_request(request)

    return route_result(operation)


@router.post("/testlib-link")
def api_testlib_link(request: Request) -> dict:
    """testlib link 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 testlib link 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "testlib linking")
        return link_testlib(workspace_from_request(request))

    return route_result(operation)


@router.delete("/packs")
def api_workspace_generated_packs_remove(
    request: Request,
    body: GeneratedPackRemoveRequest,
) -> dict:
    """현재 작업공간에서 생성된 모든 문제 팩 산출물을 제거합니다."""

    def operation() -> dict:
        ensure_local_write_allowed(request, "generated pack removal")
        active_pack_jobs = [
            job
            for job in jobs_from_request(request).list()
            if job.kind in {"pack-build", "workspace-pack-build"}
            and job.status in ACTIVE_STATUSES
            and job_matches_active_repository(request, job)
        ]
        if active_pack_jobs:
            raise JudgeError("팩 빌드가 진행 중일 때는 생성된 문제 팩을 제거할 수 없습니다.")
        return remove_generated_problem_packs(
            workspace_from_request(request),
            body.confirm_phrase,
        )

    return route_result(operation)
