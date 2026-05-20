from __future__ import annotations

from fastapi import APIRouter, Request

from judge.core.compiler import compile_problem_tool, compile_problem_tools
from judge.core.paths import rel
from problem_studio.web.routes.common import route_result, workspace_from_request
from problem_studio.web.schemas import ToolCompileRequest

router = APIRouter(prefix="/api/problems/{problem_id}/tools", tags=["tools"])


@router.post("/compile")
def api_tools_compile(
    request: Request, problem_id: str, body: ToolCompileRequest | None = None
) -> dict:
    """Compile all problem tools or one selected tool."""

    def operation() -> dict:
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
