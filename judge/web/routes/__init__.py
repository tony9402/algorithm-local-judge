from __future__ import annotations

from fastapi import APIRouter

from judge.web.routes import cache, dashboard, generation, packs, problems, runs

API_ROUTERS: tuple[APIRouter, ...] = (
    dashboard.router,
    problems.router,
    packs.router,
    generation.router,
    runs.router,
    cache.router,
)
