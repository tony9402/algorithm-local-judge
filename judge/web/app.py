from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response

from judge.web.routes import API_ROUTERS

WEB_ROOT = Path(__file__).resolve().parent
PACKAGE_STATIC_ROOT = WEB_ROOT / "static"
STANDALONE_STATIC_ROOT = Path(sys.argv[0]).resolve().parent / "web" / "static"
STATIC_ROOT = PACKAGE_STATIC_ROOT if PACKAGE_STATIC_ROOT.exists() else STANDALONE_STATIC_ROOT
INDEX_PATH = STATIC_ROOT / "index.html"


def register_api_routes(app: FastAPI) -> None:
    """Register all web API routers."""
    for router in API_ROUTERS:
        app.include_router(router)


def create_app() -> FastAPI:
    """Create the FastAPI application for the local judge UI."""
    app = FastAPI(title="Algorithm Local Judge", docs_url=None, redoc_url=None)
    register_api_routes(app)

    @app.get("/")
    def index() -> FileResponse:
        """Serve the single-page web UI."""
        return FileResponse(
            INDEX_PATH,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/static/{filename}")
    def static_file(filename: str) -> FileResponse:
        """Serve web UI assets without browser cache reuse during local development."""
        path = STATIC_ROOT / filename
        if not path.is_file():
            return Response(status_code=404)
        return FileResponse(
            path,
            headers={"Cache-Control": "no-store"},
        )

    return app


app = create_app()
