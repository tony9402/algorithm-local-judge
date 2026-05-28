"""브라우저 기반 종단 간 테스트에서 로컬 서버 실행, Playwright 페이지 생성, 화면 배치 검증을 공통으로 제공하는 모듈입니다."""

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
    """테스트 서버를 충돌 없이 띄우기 위해 현재 호스트에서 사용할 수 있는 임시 TCP 포트를 찾습니다.

    Returns:
        int: 로컬 테스트 서버가 바인딩할 수 있는 사용 가능한 TCP 포트 번호입니다.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_http(url: str, timeout: float = 10.0) -> None:
    """로컬 HTTP 엔드포인트가 요청을 받을 준비가 될 때까지 짧게 재시도합니다.

    Args:
        url (str): 응답 준비 상태를 확인할 HTTP 주소입니다.
        timeout (float): 조건이 만족될 때까지 기다릴 최대 시간입니다.
    """
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
    """테스트 중 기동한 로컬 HTTP 서버의 접속 주소와 포트를 함께 보관하는 값 객체입니다."""

    url: str
    port: int


@contextlib.contextmanager
def run_app(app: Any) -> Iterator[LocalServer]:
    """ASGI 애플리케이션을 실제 Uvicorn 서버로 띄워 브라우저 테스트가 HTTP 경계를 통과하게 합니다.

    Args:
        app (Any): 테스트 중 실제 HTTP 서버 뒤에서 실행할 ASGI 애플리케이션입니다.

    Returns:
        Iterator[LocalServer]: 실행 중인 로컬 서버의 주소와 포트 정보를 담은 컨텍스트 관리자입니다.
    """
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
    """Playwright 브라우저와 페이지 오류 수집을 공통으로 준비하는 브라우저 종단 간 테스트 기반 클래스입니다."""

    browser: Browser
    _playwright_manager: Any

    @classmethod
    def setUpClass(cls) -> None:
        """브라우저 종단 간 테스트 전체에서 공유할 Playwright 리소스의 생명주기를 관리합니다."""
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
        """브라우저 종단 간 테스트 전체에서 공유할 Playwright 리소스의 생명주기를 관리합니다."""
        cls.browser.close()
        cls._playwright_manager.stop()
        super().tearDownClass()

    def new_page(self, base_url: str, *, width: int = 1440, height: int = 900) -> Page:
        """새 브라우저 페이지를 만들고 콘솔 오류와 페이지 오류를 수집하도록 이벤트 핸들러를 연결합니다.

        Args:
            base_url (str): 브라우저 페이지가 접근할 테스트 서버의 기준 주소입니다.
            width (int): 브라우저 뷰포트 너비입니다.
            height (int): 브라우저 뷰포트 높이입니다.

        Returns:
            Page: 오류 수집과 기본 타임아웃이 설정된 새 브라우저 페이지입니다.
        """
        self.browser_errors: list[str] = []
        context = self.browser.new_context(viewport={"width": width, "height": height})
        context.set_default_timeout(15_000)
        page = context.new_page()

        def app_url(url: str) -> bool:
            """브라우저 오류 수집 대상 URL이 테스트 애플리케이션에서 온 요청인지 판정합니다.

            Args:
                url (str): 응답 준비 상태를 확인할 HTTP 주소입니다.

            Returns:
                bool: 조건을 만족하는지 나타내는 참거짓 값입니다.
            """
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
        """브라우저 실행 중 수집된 콘솔 오류와 페이지 오류가 없는지 확인합니다."""
        self.assertEqual(self.browser_errors, [])


def wait_for_text(page: Page, selector: str, text: str, timeout: int = 15_000) -> None:
    """브라우저 화면에서 텍스트 조건이 만족될 때까지 기다려 비동기 렌더링 경합을 줄입니다.

    Args:
        page (Page): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        selector (str): 브라우저에서 대상 요소를 찾기 위한 CSS 선택자입니다.
        text (str): 파일에 기록하거나 브라우저에서 기다릴 텍스트입니다.
        timeout (int): 조건이 만족될 때까지 기다릴 최대 시간입니다.
    """
    page.wait_for_function(
        """([selector, text]) => {
            const element = document.querySelector(selector);
            return Boolean(element && element.textContent.includes(text));
        }""",
        arg=[selector, text],
        timeout=timeout,
    )


def wait_for_value(page: Page, selector: str, value: str, timeout: int = 15_000) -> None:
    """브라우저 화면에서 값 조건이 만족될 때까지 기다려 비동기 렌더링 경합을 줄입니다.

    Args:
        page (Page): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        selector (str): 브라우저에서 대상 요소를 찾기 위한 CSS 선택자입니다.
        value (str): 해시하거나 입력창에 설정하거나 비교할 값입니다.
        timeout (int): 조건이 만족될 때까지 기다릴 최대 시간입니다.
    """
    page.wait_for_function(
        """([selector, value]) => {
            const element = document.querySelector(selector);
            return Boolean(element && element.value === value);
        }""",
        arg=[selector, value],
        timeout=timeout,
    )


def assert_visible_in_viewport(test: unittest.TestCase, locator: Locator) -> None:
    """요소의 화면 좌표가 현재 브라우저 뷰포트 안에 들어오는지 확인합니다.

    Args:
        test (unittest.TestCase): 검증 실패를 보고할 테스트 케이스 인스턴스입니다.
        locator (Locator): 위치나 겹침 상태를 확인할 Playwright 요소 핸들입니다.
    """
    box = locator.bounding_box()
    test.assertIsNotNone(box)
    viewport = locator.page.viewport_size or {"width": 0, "height": 0}
    test.assertGreaterEqual(box["x"] + box["width"], 0)
    test.assertGreaterEqual(box["y"] + box["height"], 0)
    test.assertLessEqual(box["x"], viewport["width"])
    test.assertLessEqual(box["y"], viewport["height"])


def assert_no_overlap(test: unittest.TestCase, first: Locator, second: Locator) -> None:
    """두 요소의 화면 좌표가 서로 겹치지 않는지 확인합니다.

    Args:
        test (unittest.TestCase): 검증 실패를 보고할 테스트 케이스 인스턴스입니다.
        first (Locator): 겹침 여부를 확인할 첫 번째 브라우저 요소입니다.
        second (Locator): 겹침 여부를 확인할 두 번째 브라우저 요소입니다.
    """
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
