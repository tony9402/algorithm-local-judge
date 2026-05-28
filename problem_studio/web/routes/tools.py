"""도구 API 요청을 서비스 계층 호출과 HTTP 응답으로 연결합니다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from judge.core.compiler import compile_problem_tool, compile_problem_tools
from judge.core.paths import rel
from problem_studio.web.routes.common import (
    enqueue_background_job,
    jobs_from_request,
    route_result,
    scoped_lane,
    to_http_error,
    workspace_from_request,
)
from problem_studio.web.schemas import ToolCompileRequest
from problem_studio.web.security_policy import ensure_local_write_allowed

router = APIRouter(prefix="/api/problems/{problem_id}/tools", tags=["tools"])


@router.post("/compile")
def api_tools_compile(
    request: Request, problem_id: str, body: ToolCompileRequest | None = None
) -> dict:
    """도구 컴파일 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (ToolCompileRequest | None): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 도구 컴파일 데이터입니다.
    """

    def operation() -> dict:
        ensure_local_write_allowed(request, "tool compilation")
        workspace = workspace_from_request(request)
        if body is not None and body.tool:
            path = compile_problem_tool(problem_id, body.tool, workspace)
            tools = {body.tool: path}
        else:
            tools = compile_problem_tools(problem_id, workspace)
        return {
            "problemId": problem_id,
            "tools": {name: str(path) for name, path in tools.items()},
            "labels": {name: rel(path, workspace) for name, path in tools.items()},
        }

    return route_result(operation)


@router.post("/compile/jobs")
def api_tools_compile_job(
    request: Request, problem_id: str, body: ToolCompileRequest | None = None
) -> dict:
    """도구 컴파일 작업 요청을 검증하고 서비스 계층에서 만든 데이터를 HTTP 응답으로 돌려줍니다.

    Args:
        request (Request): FastAPI 요청 객체입니다. 앱 상태, 작업 큐, 보안 정책 판단에 사용합니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        body (ToolCompileRequest | None): API 요청 본문을 검증한 스키마 객체입니다.

    Returns:
        dict: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 도구 컴파일 작업 데이터입니다.
    """
    try:
        ensure_local_write_allowed(request, "tool compilation")
        workspace = workspace_from_request(request)
        jobs = jobs_from_request(request)
        tool = body.tool if body is not None else None
        title = f"{tool} 컴파일 · {problem_id}" if tool else f"전체 도구 컴파일 · {problem_id}"

        def operation(cancel_token, progress):
            progress(title, label="도구 컴파일")
            cancel_token.check()
            if tool:
                path = compile_problem_tool(problem_id, tool, workspace)
                tools = {tool: path}
            else:
                tools = compile_problem_tools(problem_id, workspace, progress=progress)
            cancel_token.check()
            return {
                "problemId": problem_id,
                "tools": {name: str(path) for name, path in tools.items()},
                "labels": {name: rel(path, workspace) for name, path in tools.items()},
            }

        job = enqueue_background_job(
            jobs,
            request=request,
            kind="tool-compile",
            title=title,
            problem_id=problem_id,
            lane=scoped_lane(request, problem_id, "compile"),
            target={"problemId": problem_id, "tool": tool},
            operation=operation,
        )
        return jobs.job_dict(job)
    except Exception as exc:
        raise to_http_error(exc) from exc
