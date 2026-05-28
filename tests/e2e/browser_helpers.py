from __future__ import annotations

import contextlib
import socket
import threading
import time
import unittest
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import uvicorn

try:
    from playwright.sync_api import Browser, Locator, Page, sync_playwright
    from playwright.sync_api import Error as PlaywrightError
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without E2E deps.
    Browser = Locator = Page = Any
    PlaywrightError = Exception
    sync_playwright = None
    PLAYWRIGHT_IMPORT_ERROR = exc
else:
    PLAYWRIGHT_IMPORT_ERROR = None


def free_port() -> int:
    """Return an available localhost TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_http(url: str, timeout: float = 10.0) -> None:
    """Wait until a local HTTP endpoint returns any response."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status < 500:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
        time.sleep(0.05)
    raise AssertionError(f"server did not become ready at {url}: {last_error}")


@dataclass
class LocalServer:
    url: str
    port: int


@contextlib.contextmanager
def run_app(app: Any) -> Iterator[LocalServer]:
    """Run a FastAPI app behind a real HTTP server for browser E2E tests."""
    port = free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name=f"e2e-uvicorn-{port}", daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    try:
        wait_for_http(f"{url}/")
        yield LocalServer(url=url, port=port)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


class BrowserE2ETestCase(unittest.TestCase):
    """Base class that fails tests on browser runtime errors."""

    browser: Browser
    _playwright_manager: Any

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if sync_playwright is None:
            raise unittest.SkipTest(
                "playwright is required for browser E2E; run make e2e-install"
            ) from PLAYWRIGHT_IMPORT_ERROR
        cls._playwright_manager = sync_playwright().start()
        try:
            cls.browser = cls._playwright_manager.chromium.launch(headless=True)
        except PlaywrightError as exc:
            cls._playwright_manager.stop()
            raise AssertionError(
                "Playwright Chromium is required for E2E tests. "
                "Run `make e2e-install` before `make e2e`."
            ) from exc

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls._playwright_manager.stop()
        super().tearDownClass()

    def new_page(self, base_url: str, *, width: int = 1440, height: int = 900) -> Page:
        self.browser_errors: list[str] = []
        context = self.browser.new_context(viewport={"width": width, "height": height})
        context.set_default_timeout(15_000)
        page = context.new_page()

        def app_url(url: str) -> bool:
            return url.startswith(base_url) and not url.endswith("/favicon.ico")

        page.on("pageerror", lambda exc: self.browser_errors.append(f"pageerror: {exc}"))
        page.on(
            "console",
            lambda message: (
                self.browser_errors.append(f"console.error: {message.text}")
                if message.type == "error"
                else None
            ),
        )
        page.on(
            "requestfailed",
            lambda request: (
                self.browser_errors.append(
                    f"request failed: {request.method} {request.url} {request.failure or ''}"
                )
                if app_url(request.url) and "net::ERR_ABORTED" not in (request.failure or "")
                else None
            ),
        )
        page.on(
            "response",
            lambda response: (
                self.browser_errors.append(f"http {response.status}: {response.url}")
                if app_url(response.url) and response.status >= 400
                else None
            ),
        )
        self.addCleanup(context.close)
        return page

    def assert_no_browser_errors(self) -> None:
        self.assertEqual(self.browser_errors, [])


def wait_for_text(page: Page, selector: str, text: str, timeout: int = 15_000) -> None:
    page.wait_for_function(
        """([selector, text]) => {
            const element = document.querySelector(selector);
            return Boolean(element && element.textContent.includes(text));
        }""",
        arg=[selector, text],
        timeout=timeout,
    )


def wait_for_value(page: Page, selector: str, value: str, timeout: int = 15_000) -> None:
    page.wait_for_function(
        """([selector, value]) => {
            const element = document.querySelector(selector);
            return Boolean(element && element.value === value);
        }""",
        arg=[selector, value],
        timeout=timeout,
    )


def assert_visible_in_viewport(test: unittest.TestCase, locator: Locator) -> None:
    box = locator.bounding_box()
    test.assertIsNotNone(box)
    viewport = locator.page.viewport_size or {"width": 0, "height": 0}
    test.assertGreaterEqual(box["x"] + box["width"], 0)
    test.assertGreaterEqual(box["y"] + box["height"], 0)
    test.assertLessEqual(box["x"], viewport["width"])
    test.assertLessEqual(box["y"], viewport["height"])


def assert_no_overlap(test: unittest.TestCase, first: Locator, second: Locator) -> None:
    a = first.bounding_box()
    b = second.bounding_box()
    test.assertIsNotNone(a)
    test.assertIsNotNone(b)
    separated = (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )
    test.assertTrue(separated, f"elements overlap: {a} vs {b}")
