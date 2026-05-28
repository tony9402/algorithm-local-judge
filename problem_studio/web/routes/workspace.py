"""workspace 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from problem_studio.core.workspace import link_testlib, resolve_workspace
from problem_studio.web.routes.common import (
    route_result,
    workspace_from_request,
    workspace_status_from_request,
)
from problem_studio.web.schemas import WorkspaceOpenRequest
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("")
def api_workspace(request: Request) -> dict:
    """api_workspace 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
    return route_result(lambda: workspace_status_from_request(request))


@router.post("/open")
def api_workspace_open(request: Request, body: WorkspaceOpenRequest) -> dict:
    """api_workspace_open 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
        body (WorkspaceOpenRequest): `body` 값입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """

    def operation() -> dict:
    """operation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
        ensure_local_write_allowed(request, "workspace switching")
        request.app.state.workspace_root = resolve_workspace(body.path)
        request.app.state.active_repository = None
        request.app.state.workspace = request.app.state.workspace_root
        return workspace_status_from_request(request)

    return route_result(operation)


@router.post("/testlib-link")
def api_testlib_link(request: Request) -> dict:
    """api_testlib_link 함수를 실행하고 결과를 반환합니다.
    
    Args:
        request (Request): HTTP 요청 객체입니다.
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """

    def operation() -> dict:
    """operation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict: 처리 결과를 반환합니다.
    """
        ensure_local_write_allowed(request, "testlib linking")
        return link_testlib(workspace_from_request(request))

    return route_result(operation)
