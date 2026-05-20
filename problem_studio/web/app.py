from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response

from problem_studio.core.workspace import resolve_workspace
from problem_studio.web.jobs import BackgroundJobStore
from problem_studio.web.routes import API_ROUTERS

WEB_ROOT = Path(__file__).resolve().parent
PACKAGE_STATIC_ROOT = WEB_ROOT / "static"
STANDALONE_STATIC_ROOT = Path(sys.argv[0]).resolve().parent / "problem-studio" / "static"
STATIC_ROOT = PACKAGE_STATIC_ROOT if PACKAGE_STATIC_ROOT.exists() else STANDALONE_STATIC_ROOT
INDEX_PATH = STATIC_ROOT / "index.html"


def register_api_routes(app: FastAPI) -> None:
    """Register all problem-studio API routers."""
    for router in API_ROUTERS:
        app.include_router(router)


def create_app(workspace: Path | str | None = None) -> FastAPI:
    """Create the FastAPI application for problem authoring."""
    app = FastAPI(title="Problem Studio", docs_url=None, redoc_url=None)
    app.state.workspace = resolve_workspace(workspace)
    app.state.jobs = BackgroundJobStore()
    register_api_routes(app)

    @app.get("/")
    def index() -> FileResponse:
        """Serve the single-page problem authoring UI."""
        return FileResponse(INDEX_PATH, headers={"Cache-Control": "no-store"})

    @app.get("/static/{filename:path}")
    def static_file(filename: str) -> FileResponse:
        """Serve static assets without browser cache reuse during local development."""
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
