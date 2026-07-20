from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JudgeRecentResultUiContractTest(unittest.TestCase):
    def test_recent_result_anchor_reuses_the_existing_result_modal(self) -> None:
        page = (ROOT / "judge/web/static/index.html").read_text(encoding="utf-8")
        run = (ROOT / "judge/web/static/app/run.js").read_text(encoding="utf-8")
        events = (ROOT / "judge/web/static/app/events.js").read_text(encoding="utf-8")

        self.assertIn('id="lastResultAnchor"', page)
        self.assertIn('id="lastResultButton"', page)
        self.assertIn("renderLastResultAnchor(result)", run)
        self.assertIn("app.showResultModal(state.lastRunResult)", events)

    def test_primary_text_uses_theme_specific_contrast_token(self) -> None:
        stylesheet = (ROOT / "judge/web/static/styles/base.css").read_text(encoding="utf-8")

        self.assertGreaterEqual(stylesheet.count("--primary-text:"), 2)
        self.assertIn("color: var(--primary-text)", stylesheet)
        dark_tokens = stylesheet.split(':root[data-theme="dark"]', 1)[1].split("}", 1)[0]
        colors = dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", dark_tokens))
        self.assertGreaterEqual(self._contrast(colors["accent"], colors["primary-text"]), 4.5)
        self.assertGreaterEqual(self._contrast(colors["accent-dark"], colors["primary-text"]), 4.5)

    def test_mobile_core_controls_have_44px_targets(self) -> None:
        stylesheet = (ROOT / "judge/web/static/styles/responsive.css").read_text(encoding="utf-8")

        self.assertIn("#problemJumpButton", stylesheet)
        self.assertIn("#sampleRunButton", stylesheet)
        self.assertIn("#jobsButton", stylesheet)
        self.assertIn("min-height: 44px", stylesheet)

    @staticmethod
    def _contrast(first: str, second: str) -> float:
        def luminance(color: str) -> float:
            channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [
                value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                for value in channels
            ]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
        return (lighter + 0.05) / (darker + 0.05)


if __name__ == "__main__":
    unittest.main()
