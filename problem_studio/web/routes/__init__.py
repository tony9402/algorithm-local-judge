"""__init__ 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from fastapi import APIRouter

from problem_studio.web.routes import (
    bulk,
    cases,
    checks,
    files,
    git,
    jobs,
    packs,
    problems,
    repositories,
    solutions,
    tools,
    workspace,
)

API_ROUTERS: tuple[APIRouter, ...] = (
    workspace.router,
    jobs.router,
    git.router,
    repositories.router,
    problems.router,
    files.router,
    cases.router,
    checks.router,
    tools.router,
    solutions.router,
    packs.router,
    bulk.router,
)
