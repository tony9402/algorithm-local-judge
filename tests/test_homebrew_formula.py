"""Homebrew release formula generation contracts."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.build_homebrew_formula import formula_text, version_from_tag


class HomebrewFormulaTest(unittest.TestCase):
    def test_formula_pins_all_supported_first_phase_assets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-homebrew-") as tmp:
            assets = Path(tmp)
            payloads = {
                "macos-arm64": b"mac-arm",
                "macos-amd64": b"mac-intel",
                "linux-amd64": b"linux",
            }
            for platform, payload in payloads.items():
                (assets / f"algorithm-local-judge-1.2.3-{platform}.tar.gz").write_bytes(payload)
            formula = formula_text(assets, "v1.2.3")

        self.assertIn('version "1.2.3"', formula)
        for platform, payload in payloads.items():
            self.assertIn(f"algorithm-local-judge-1.2.3-{platform}.tar.gz", formula)
            self.assertIn(hashlib.sha256(payload).hexdigest(), formula)
        self.assertIn("Hardware::CPU.arm?", formula)
        self.assertIn('bin.install_symlink libexec/"algorithm-local-judge/bin/judge"', formula)
        self.assertIn(
            'bin.install_symlink libexec/"algorithm-local-judge/bin/problem-studio"',
            formula,
        )
        self.assertIn('shell_output("#{bin}/problem-studio --help")', formula)
        self.assertIn('system bin/"judge", "setup", "--check-only"', formula)

    def test_tag_must_be_numeric_release_version(self) -> None:
        self.assertEqual(version_from_tag("v0.1.0"), "0.1.0")
        with self.assertRaises(ValueError):
            version_from_tag("latest")


if __name__ == "__main__":
    unittest.main()
