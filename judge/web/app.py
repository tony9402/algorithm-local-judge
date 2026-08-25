"""애플리케이션 웹 백엔드 구성과 응답 데이터 조립을 담당합니다."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response

from commons.job_persistence import default_job_history_path
from commons.job_queue import BackgroundJobStore
from commons.web_observability import default_readiness, register_web_observability
from commons.web_security import install_request_security_middleware
from judge.web.routes import API_ROUTERS
from judge.web.submission_rate_limit import SubmissionRateLimiter
from judge.web.submission_store import SubmissionStore

WEB_ROOT = Path(__file__).resolve().parent
PACKAGE_STATIC_ROOT = WEB_ROOT / "static"
STANDALONE_STATIC_ROOT = Path(sys.argv[0]).resolve().parent / "web" / "static"
STATIC_ROOT = PACKAGE_STATIC_ROOT if PACKAGE_STATIC_ROOT.exists() else STANDALONE_STATIC_ROOT
INDEX_PATH = STATIC_ROOT / "index.html"


def register_api_routes(app: FastAPI) -> None:
    for router in API_ROUTERS:
        app.include_router(router)


def judge_readiness(app: FastAPI) -> tuple[bool, dict[str, str]]:
    _ready, checks = default_readiness(app)
    checks["static"] = "ok" if INDEX_PATH.is_file() else "missing"
    return all(value == "ok" for value in checks.values()), checks


def create_app(
    *,
    local_binding: bool = True,
    remote_warning: bool = False,
    allow_remote_run: bool = False,
    allow_remote_write: bool = False,
    job_history_path: Path | str | None = None,
    submission_history_root: Path | str | None = None,
    legacy_source_history_root: Path | str | None = None,
) -> FastAPI:
    """로컬 judge 웹 UI에 필요한 라우터, 보안 상태, 작업 큐를 가진 FastAPI 앱을 만듭니다.

    Args:
        local_binding (bool): 애플리케이션 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        remote_warning (bool): 애플리케이션 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        allow_remote_run (bool): 애플리케이션 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        allow_remote_write (bool): 비로컬 바인딩에서 관리 API를 허용할지 결정합니다.
        job_history_path (Path | str | None): 재시작 복원용 작업 이력 파일 경로입니다.

    Returns:
        FastAPI: 라우터와 정적 파일 설정이 등록된 FastAPI 애플리케이션입니다.
    """
    app = FastAPI(title="Algorithm Local Judge", docs_url=None, redoc_url=None)
    install_request_security_middleware(app)
    app.state.local_binding = local_binding
    app.state.remote_warning = remote_warning
    app.state.allow_remote_run = allow_remote_run
    app.state.allow_remote_write = allow_remote_write
    app.state.jobs = BackgroundJobStore(
        max_running_jobs=4,
        persistence_path=job_history_path,
    )
    app.state.submissions = SubmissionStore(
        submission_history_root,
        legacy_source_history_root,
    )
    app.state.submission_rate_limiter = SubmissionRateLimiter()
    register_web_observability(app, "judge", judge_readiness)
    register_api_routes(app)

    @app.get("/")
    def index() -> FileResponse:
        """단일 페이지 judge 웹 UI의 index.html을 반환합니다."""
        return FileResponse(
            INDEX_PATH,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/static/{file_path:path}")
    def static_file(file_path: str) -> FileResponse:
        """로컬 개발 중 캐시 재사용을 막고 정적 파일을 안전한 경로에서 반환합니다."""
        root = STATIC_ROOT.resolve()
        path = (root / file_path).resolve()
        if root not in path.parents and path != root:
            return Response(status_code=404)
        if not path.is_file():
            return Response(status_code=404)
        return FileResponse(
            path,
            headers={"Cache-Control": "no-store"},
        )

    return app


app = create_app(job_history_path=default_job_history_path("judge"))
