"""웹 브라우저에서 발생하는 교차 출처 상태 변경을 차단합니다.

Judge와 Problem Studio는 기본적으로 loopback에서만 실행되지만, 브라우저의
CSRF 공격은 인증 없이도 loopback HTTP API를 호출할 수 있습니다. 이 모듈은
두 애플리케이션이 동일한 Origin/Fetch Metadata 규칙을 사용하도록 작은 ASGI
미들웨어를 제공합니다.

Origin, Referer, Fetch Metadata 헤더가 전혀 없는 요청은 CLI와 기존 API
클라이언트의 호환성을 위해 허용합니다. 브라우저가 해당 헤더를 보낸 경우에는
모든 신호가 현재 요청의 origin과 일치해야 합니다.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
BLOCKED_FETCH_SITES = frozenset({"cross-site", "same-site"})


def _default_port(scheme: str) -> int | None:
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    return None


def _origin_tuple(value: str, *, allow_path: bool = False) -> tuple[str, str, int | None] | None:
    """Return a normalized origin tuple, optionally accepting a URL path."""
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password or (not allow_path and parsed.path not in {"", "/"}):
        return None
    if not allow_path and (parsed.query or parsed.fragment):
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    return parsed.scheme.lower(), parsed.hostname.lower(), port or _default_port(parsed.scheme)


def _request_origin(request: Request) -> tuple[str, str, int | None]:
    scheme = request.url.scheme.lower()
    hostname = (request.url.hostname or "").lower()
    return scheme, hostname, request.url.port or _default_port(scheme)


def _same_origin(value: str, request: Request, *, allow_path: bool = False) -> bool:
    parsed = _origin_tuple(value, allow_path=allow_path)
    return parsed is not None and parsed == _request_origin(request)


def request_context_violation(request: Request) -> str | None:
    """Return a short reason when a state-changing request is cross-origin.

    A missing browser context header is intentionally accepted for backwards
    compatibility with command-line/API clients. Presence of any browser
    context signal opts the request into strict validation.
    """
    if request.method.upper() not in STATE_CHANGING_METHODS:
        return None

    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()

    if fetch_site in BLOCKED_FETCH_SITES:
        return "cross-origin browser request rejected"
    if origin:
        if not _same_origin(origin, request):
            return "request Origin does not match the server origin"
        return None
    if referer and not _same_origin(referer, request, allow_path=True):
        return "request Referer does not match the server origin"
    return None


def install_request_security_middleware(app: FastAPI) -> None:
    """Install the shared browser-origin guard on a FastAPI application."""

    @app.middleware("http")
    async def _request_security_guard(request: Request, call_next):
        reason = request_context_violation(request)
        if reason:
            return JSONResponse(
                status_code=403,
                content={"detail": reason},
                headers={
                    "Cache-Control": "no-store",
                    "Vary": "Origin, Referer, Sec-Fetch-Site",
                },
            )
        response = await call_next(request)
        response.headers.setdefault("Vary", "Origin, Referer, Sec-Fetch-Site")
        return response


__all__ = [
    "BLOCKED_FETCH_SITES",
    "STATE_CHANGING_METHODS",
    "install_request_security_middleware",
    "request_context_violation",
]
