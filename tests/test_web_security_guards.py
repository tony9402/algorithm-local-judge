"""Regression tests for browser-origin and local-file web guards."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

from commons.web_security import request_context_violation
from judge.core.errors import JudgeError
from judge.web.source_request import source_path_from_request


def make_request(method: str, headers: dict[str, str] | None = None) -> Request:
    encoded_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/api/run",
        "raw_path": b"/api/run",
        "query_string": b"",
        "headers": encoded_headers,
        "client": ("127.0.0.1", 54321),
        "server": ("127.0.0.1", 9891),
    }
    return Request(scope)


class WebSecurityGuardTest(unittest.TestCase):
    def test_missing_browser_headers_remains_compatible_with_api_clients(self) -> None:
        self.assertIsNone(request_context_violation(make_request("POST")))

    def test_same_origin_origin_and_referer_are_allowed(self) -> None:
        self.assertIsNone(
            request_context_violation(make_request("POST", {"Origin": "http://127.0.0.1:9891"}))
        )
        self.assertIsNone(
            request_context_violation(
                make_request(
                    "POST",
                    {
                        "Referer": "http://127.0.0.1:9891/judge?tab=run",
                        "Sec-Fetch-Site": "same-origin",
                    },
                )
            )
        )

    def test_cross_origin_browser_signals_are_rejected(self) -> None:
        self.assertIsNotNone(
            request_context_violation(make_request("POST", {"Origin": "https://evil.example"}))
        )
        self.assertIsNotNone(
            request_context_violation(
                make_request("POST", {"Referer": "https://evil.example/form"})
            )
        )
        self.assertIsNotNone(
            request_context_violation(make_request("POST", {"Sec-Fetch-Site": "cross-site"}))
        )

    def test_safe_methods_are_not_subject_to_csrf_guard(self) -> None:
        self.assertIsNone(
            request_context_violation(make_request("GET", {"Origin": "https://evil.example"}))
        )

    def test_source_path_is_limited_to_temp_or_history_roots(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-source-guard-") as tmp:
            cache = Path(tmp) / "cache"
            source = Path(tmp) / "main.py"
            source.write_text("print(1)\n", encoding="utf-8")
            with patch.dict(os.environ, {"ALJ_CACHE_HOME": str(cache)}, clear=False):
                saved = source_path_from_request(
                    "06", "path", str(source), None, source.name, "python"
                )
                self.assertTrue(saved.is_file())
                with self.assertRaises(JudgeError):
                    source_path_from_request("06", "path", "/etc/passwd", None, "passwd", "text")


if __name__ == "__main__":
    unittest.main()
