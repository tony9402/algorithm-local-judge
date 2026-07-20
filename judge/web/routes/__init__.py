from __future__ import annotations

from fastapi import APIRouter

from judge.web.routes import (
    cache,
    dashboard,
    generation,
    jobs,
    packs,
    problems,
    runs,
    sources,
    submissions,
)

API_ROUTERS: tuple[APIRouter, ...] = (
    dashboard.router,
    jobs.router,
    problems.router,
    packs.router,
    generation.router,
    runs.router,
    submissions.router,
    sources.router,
    cache.router,
)
