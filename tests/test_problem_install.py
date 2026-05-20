from __future__ import annotations

import unittest

from judge.core.errors import JudgeError
from judge.core.remote import github_repository_from_source, select_pack_asset


class ProblemInstallTest(unittest.TestCase):
    """Tests for easy problem installation helpers."""

    def test_github_repository_from_source_accepts_common_forms(self) -> None:
        """Repository input should work with owner/name, HTTPS, and SSH forms."""
        self.assertEqual(
            github_repository_from_source("tony9402/algorithm-modules"),
            "tony9402/algorithm-modules",
        )
        self.assertEqual(
            github_repository_from_source("https://github.com/tony9402/algorithm-modules"),
            "tony9402/algorithm-modules",
        )
        self.assertEqual(
            github_repository_from_source("git@github.com:tony9402/algorithm-modules.git"),
            "tony9402/algorithm-modules",
        )

    def test_github_repository_from_source_rejects_non_github_source(self) -> None:
        """Non-GitHub strings should be left for other installers to handle."""
        self.assertIsNone(github_repository_from_source("not a repository"))
        self.assertIsNone(github_repository_from_source("https://example.com/owner/repo"))

    def test_select_pack_asset_prefers_requested_asset(self) -> None:
        """Explicit asset names should pick the matching .aljpack asset."""
        assets = [
            {"name": "notes.txt", "browser_download_url": "https://example.com/notes.txt"},
            {
                "name": "basic-1-macos-arm64.aljpack",
                "browser_download_url": "https://example.com/basic.aljpack",
            },
        ]

        selected = select_pack_asset(assets, "basic-1-macos-arm64.aljpack")

        self.assertEqual(selected["name"], "basic-1-macos-arm64.aljpack")

    def test_select_pack_asset_requires_pack_assets(self) -> None:
        """Missing release pack assets should be reported clearly."""
        with self.assertRaises(JudgeError):
            select_pack_asset([{"name": "notes.txt"}], None)


if __name__ == "__main__":
    unittest.main()
