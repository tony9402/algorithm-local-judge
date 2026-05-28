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
