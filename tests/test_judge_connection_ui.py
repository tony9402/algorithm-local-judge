from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JudgeConnectionUiContractTest(unittest.TestCase):
    def test_first_viewport_connection_retry_contract_is_present(self) -> None:
        page = (ROOT / "judge/web/static/index.html").read_text(encoding="utf-8")
        app = (ROOT / "judge/web/static/app.js").read_text(encoding="utf-8")
        connection = (ROOT / "judge/web/static/app/connection.js").read_text(encoding="utf-8")

        self.assertIn('id="connectionBanner"', page)
        self.assertIn('id="connectionRetryButton"', page)
        self.assertIn('role="alert"', page)
        self.assertIn('import "./app/connection.js"', app)
        self.assertIn("if (state.connectionRetrying) return", connection)
        self.assertIn("showConnectionError", connection)

    def test_secondary_refresh_isolated_by_region(self) -> None:
        refresh = (ROOT / "judge/web/static/app/refresh.js").read_text(encoding="utf-8")
        connection = (ROOT / "judge/web/static/app/connection.js").read_text(encoding="utf-8")

        self.assertIn("Promise.allSettled", refresh)
        self.assertIn("showSecondaryError", refresh)
        self.assertIn('"recent-submissions"', refresh)
        self.assertIn("data-secondary-retry", connection)
        self.assertIn("refreshSecondaryRegion", connection)

    def test_stale_core_connection_attempt_cannot_replace_current_state(self) -> None:
        refresh = (ROOT / "judge/web/static/app/refresh.js").read_text(encoding="utf-8")
        state = (ROOT / "judge/web/static/app/state.js").read_text(encoding="utf-8")

        self.assertIn("connectionAttemptToken", state)
        self.assertIn("++state.connectionAttemptToken", refresh)
        self.assertIn("attemptToken !== state.connectionAttemptToken", refresh)


if __name__ == "__main__":
    unittest.main()
