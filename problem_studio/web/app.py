"""app 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response

from problem_studio.core.repositories import initialize_problem_repository_workspace
from problem_studio.web.jobs import BackgroundJobStore
from problem_studio.web.routes import API_ROUTERS

WEB_ROOT = Path(__file__).resolve().parent
PACKAGE_STATIC_ROOT = WEB_ROOT / "static"
STANDALONE_STATIC_ROOT = Path(sys.argv[0]).resolve().parent / "problem-studio" / "static"
STATIC_ROOT = PACKAGE_STATIC_ROOT if PACKAGE_STATIC_ROOT.exists() else STANDALONE_STATIC_ROOT
INDEX_PATH = STATIC_ROOT / "index.html"
INCLUDE_PREFIX = "<!-- include:"
INCLUDE_SUFFIX = "-->"


def register_api_routes(app: FastAPI) -> None:
    """register_api_routes 함수를 실행하고 결과를 반환합니다.
    
    Args:
        app (FastAPI): `app` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    for router in API_ROUTERS:
        app.include_router(router)


def expand_static_includes(source: str, static_root: Path) -> str:
    """expand_static_includes 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (str): `source` 값입니다.
        static_root (Path): `static_root` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    rendered: list[str] = []
    cursor = 0
    while True:
        start = source.find(INCLUDE_PREFIX, cursor)
        if start < 0:
            rendered.append(source[cursor:])
            return "".join(rendered)
        end = source.find(INCLUDE_SUFFIX, start)
        if end < 0:
            rendered.append(source[cursor:])
            return "".join(rendered)
        rendered.append(source[cursor:start])
        fragment_name = source[start + len(INCLUDE_PREFIX) : end].strip()
        fragment_path = (static_root / fragment_name).resolve()
        try:
            fragment_path.relative_to(static_root)
        except ValueError as exc:
            raise RuntimeError(f"invalid static include path: {fragment_name}") from exc
        if not fragment_path.is_file():
            raise RuntimeError(f"static include not found: {fragment_name}")
        rendered.append(fragment_path.read_text(encoding="utf-8"))
        cursor = end + len(INCLUDE_SUFFIX)


def render_index_html() -> str:
    """render_index_html 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    static_root = STATIC_ROOT.resolve()
    return expand_static_includes(INDEX_PATH.read_text(encoding="utf-8"), static_root)


def create_app(
    workspace: Path | str | None = None,
    active_repository: str | None = None,
    git_write_enabled: bool = True,
    workspace_warning: bool = False,
    local_binding: bool = True,
    workspace_write_enabled: bool | None = None,
) -> FastAPI:
    """create_app 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path | str | None): 작업 공간 객체입니다.
        active_repository (str | None): `active_repository` 값입니다.
        git_write_enabled (bool): `git_write_enabled` 값입니다.
        workspace_warning (bool): `workspace_warning` 값입니다.
        local_binding (bool): `local_binding` 값입니다.
        workspace_write_enabled (bool | None): `workspace_write_enabled` 값입니다.
    
    Returns:
        FastAPI: 처리 결과를 반환합니다.
    """
    app = FastAPI(title="Problem Studio", docs_url=None, redoc_url=None)
    workspace_root, repository_name, active_workspace = initialize_problem_repository_workspace(
        workspace,
        active_repository,
    )
    app.state.workspace_root = workspace_root
    app.state.active_repository = repository_name
    app.state.workspace = active_workspace
    app.state.local_binding = local_binding
    app.state.git_write_enabled = git_write_enabled
    app.state.workspace_warning = workspace_warning
    app.state.workspace_write_enabled = (
        git_write_enabled if workspace_write_enabled is None else workspace_write_enabled
    )
    app.state.jobs = BackgroundJobStore(max_running_jobs=4)
    register_api_routes(app)

    @app.get("/")
    def index() -> HTMLResponse:
        """index 함수를 실행하고 결과를 반환합니다.
        
        Args:
            없음
        
        Returns:
            HTMLResponse: 처리 결과를 반환합니다.
        """
        return HTMLResponse(render_index_html(), headers={"Cache-Control": "no-store"})

    @app.get("/static/{filename:path}")
    def static_file(filename: str) -> FileResponse:
        """static_file 함수를 실행하고 결과를 반환합니다.
        
        Args:
            filename (str): `filename` 값입니다.
        
        Returns:
            FileResponse: 처리 결과를 반환합니다.
        """
        static_root = STATIC_ROOT.resolve()
        path = (static_root / filename).resolve()
        try:
            path.relative_to(static_root)
        except ValueError:
            return Response(status_code=404)
        if not path.is_file():
            return Response(status_code=404)
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    return app


app = create_app()
