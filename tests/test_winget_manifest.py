from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.build_windows_installer import UPGRADE_CODE
from scripts.build_winget_manifest import manifest_payloads, write_manifests


class WinGetManifestTest(unittest.TestCase):
    def test_manifest_pins_x64_wix_msi_and_both_commands(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-winget-test-") as tmp:
            root = Path(tmp)
            msi = root / "algorithm-local-judge-1.2.3-windows-amd64.msi"
            msi.write_bytes(b"unsigned-local-msi")
            url = f"https://github.com/example/alj/releases/download/v1.2.3/{msi.name}"

            payloads = manifest_payloads(
                msi,
                "Example.AlgorithmLocalJudge",
                "1.2.3",
                url,
            )
            outputs = write_manifests(payloads, root / "manifests", "Example.AlgorithmLocalJudge")
            installer = yaml.safe_load(
                next(path for path in outputs if ".installer." in path.name).read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(installer["InstallerType"], "wix")
        self.assertEqual(installer["MinimumOSVersion"], "10.0.0.0")
        self.assertEqual(installer["Commands"], ["judge", "problem-studio"])
        self.assertEqual(installer["Installers"][0]["Architecture"], "x64")
        self.assertEqual(
            installer["Installers"][0]["InstallerSha256"],
            hashlib.sha256(b"unsigned-local-msi").hexdigest().upper(),
        )
        self.assertEqual(
            installer["Installers"][0]["AppsAndFeaturesEntries"][0]["UpgradeCode"],
            UPGRADE_CODE,
        )
        self.assertIn(
            "e/Example/AlgorithmLocalJudge/1.2.3",
            next(path for path in outputs if ".installer." in path.name).as_posix(),
        )

    def test_manifest_rejects_unsupported_arch_and_mutable_url(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-winget-test-") as tmp:
            msi = Path(tmp) / "alj.msi"
            msi.write_bytes(b"msi")
            with self.assertRaisesRegex(ValueError, "unsupported WinGet platform"):
                manifest_payloads(
                    msi,
                    "Example.AlgorithmLocalJudge",
                    "1.2.3",
                    "https://example.test/alj.msi",
                    "windows-arm64",
                )
            with self.assertRaisesRegex(ValueError, "end with the MSI filename"):
                manifest_payloads(
                    msi,
                    "Example.AlgorithmLocalJudge",
                    "1.2.3",
                    "https://example.test/latest.msi",
                )


if __name__ == "__main__":
    unittest.main()
