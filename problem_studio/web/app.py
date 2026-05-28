"""애플리케이션 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
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
    for router in API_ROUTERS:
        app.include_router(router)


def expand_static_includes(source: str, static_root: Path) -> str:
    """expand static includes 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        source (str): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
        static_root (Path): expand static includes을 계산하거나 검증할 때 필요한 static root 입력입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 expand static includes 문자열입니다.
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
    """index html 데이터를 현재 DOM 구조에 맞춰 다시 그립니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 index html 문자열입니다.
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
    """애플리케이션에 필요한 초기 파일과 메타데이터를 생성합니다.

    Args:
        workspace (Path | str | None): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        active_repository (str | None): 애플리케이션을 계산하거나 검증할 때 필요한 활성 저장소 입력입니다.
        git_write_enabled (bool): 애플리케이션 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        workspace_warning (bool): 애플리케이션 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        local_binding (bool): 애플리케이션 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        workspace_write_enabled (bool | None): 애플리케이션을 계산하거나 검증할 때 필요한 작업 공간 쓰기 enabled 입력입니다.

    Returns:
        FastAPI: 라우터와 정적 파일 설정이 등록된 FastAPI 애플리케이션입니다.
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
        """문제 제작용 단일 페이지 UI의 HTML을 렌더링해 반환합니다."""
        return HTMLResponse(render_index_html(), headers={"Cache-Control": "no-store"})

    @app.get("/static/{filename:path}")
    def static_file(filename: str) -> FileResponse:
        """작업 공간 밖 경로 접근을 막고 정적 자산을 no-store 헤더와 함께 반환합니다."""
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
