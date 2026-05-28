"""__init__ 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import APIRouter

from judge.web.routes import cache, dashboard, generation, jobs, packs, problems, runs, sources

API_ROUTERS: tuple[APIRouter, ...] = (
    dashboard.router,
    jobs.router,
    problems.router,
    packs.router,
    generation.router,
    runs.router,
    sources.router,
    cache.router,
)
