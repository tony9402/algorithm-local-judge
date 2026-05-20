from __future__ import annotations

from fastapi import APIRouter

from problem_studio.web.routes import (
    bulk,
    cases,
    files,
    packs,
    problems,
    solutions,
    tools,
    workspace,
)

API_ROUTERS: tuple[APIRouter, ...] = (
    workspace.router,
    problems.router,
    files.router,
    cases.router,
    tools.router,
    solutions.router,
    packs.router,
    bulk.router,
)
