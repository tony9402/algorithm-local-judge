"""Small dependency-free health, request correlation, and metrics support."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
HTTP_LOGGER = logging.getLogger("algorithm_local_judge.http")


class WebMetrics:
    def __init__(self, app_name: str) -> None:
        self.app_name = app_name.replace("-", "_")
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, int]] = Counter()
        self._duration_seconds = 0.0
        self._in_flight = 0

    def start(self) -> None:
        with self._lock:
            self._in_flight += 1

    def finish(self, method: str, status_code: int, duration_seconds: float) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._requests[(method, status_code)] += 1
            self._duration_seconds += duration_seconds

    def render(self) -> str:
        prefix = f"alj_{self.app_name}"
        with self._lock:
            request_items = sorted(self._requests.items())
            duration = self._duration_seconds
            in_flight = self._in_flight
        lines = [
            f"# TYPE {prefix}_http_requests_total counter",
            *[
                f'{prefix}_http_requests_total{{method="{method}",status="{status}"}} {count}'
                for (method, status), count in request_items
            ],
            f"# TYPE {prefix}_http_request_duration_seconds_sum counter",
            f"{prefix}_http_request_duration_seconds_sum {duration:.9f}",
            f"# TYPE {prefix}_http_requests_in_flight gauge",
            f"{prefix}_http_requests_in_flight {in_flight}",
        ]
        return "\n".join(lines) + "\n"


def job_metrics(app: FastAPI, prefix: str) -> str:
    jobs = getattr(app.state, "jobs", None)
    if jobs is None:
        return ""
    queued = jobs.queued_count()
    running = jobs.running_count()
    retained = len(jobs.list())
    return (
        "\n".join(
            [
                f"# TYPE {prefix}_jobs gauge",
                f'{prefix}_jobs{{state="queued"}} {queued}',
                f'{prefix}_jobs{{state="running"}} {running}',
                f'{prefix}_jobs{{state="retained"}} {retained}',
            ]
        )
        + "\n"
    )


def request_id(request: Request) -> str:
    candidate = request.headers.get(REQUEST_ID_HEADER, "")
    return candidate if REQUEST_ID_RE.fullmatch(candidate) else uuid.uuid4().hex


def default_readiness(app: FastAPI) -> tuple[bool, dict[str, str]]:
    checks = {
        "jobs": "ok" if getattr(app.state, "jobs", None) is not None else "missing",
    }
    return all(value == "ok" for value in checks.values()), checks


def register_web_observability(
    app: FastAPI,
    app_name: str,
    readiness: Callable[[FastAPI], tuple[bool, dict[str, str]]] = default_readiness,
) -> None:
    metrics = WebMetrics(app_name)
    app.state.web_metrics = metrics

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[..., Any]) -> Response:
        correlation_id = request_id(request)
        request.state.request_id = correlation_id
        started = time.perf_counter()
        status_code = 500
        metrics.start()
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = correlation_id
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
            response.headers.setdefault("X-Frame-Options", "DENY")
            return response
        finally:
            duration = time.perf_counter() - started
            metrics.finish(request.method, status_code, duration)
            HTTP_LOGGER.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "app": app_name,
                        "requestId": correlation_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": status_code,
                        "durationMs": round(duration * 1000, 3),
                    },
                    separators=(",", ":"),
                )
            )

    @app.get("/healthz", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok", "app": app_name}

    @app.get("/readyz", include_in_schema=False)
    def ready() -> JSONResponse:
        is_ready, checks = readiness(app)
        return JSONResponse(
            {"status": "ready" if is_ready else "not_ready", "checks": checks},
            status_code=200 if is_ready else 503,
        )

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> PlainTextResponse:
        return PlainTextResponse(
            metrics.render() + job_metrics(app, f"alj_{metrics.app_name}"),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )


__all__ = [
    "REQUEST_ID_HEADER",
    "WebMetrics",
    "default_readiness",
    "job_metrics",
    "register_web_observability",
    "request_id",
]
