from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.build_windows_installer import (
    UPGRADE_CODE,
    WIX_NAMESPACE,
    msi_version,
    stage_windows_standalone,
    validate_windows_platform,
    wix_source,
)


class WindowsInstallerBuilderTest(unittest.TestCase):
    def test_wix_source_installs_two_launchers_path_and_stable_upgrade(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-wix-test-") as tmp:
            app = Path(tmp) / "algorithm-local-judge"
            binary = app / "bin"
            binary.mkdir(parents=True)
            (binary / "judge.exe").write_bytes(b"judge")
            (binary / "problem-studio.exe").write_bytes(b"studio")
            (binary / "web" / "static").mkdir(parents=True)
            (binary / "web" / "static" / "index.html").write_text(
                "<main></main>\n", encoding="utf-8"
            )

            source = wix_source(app, "1.2.3")
            root = ET.fromstring(source)

        namespace = {"w": WIX_NAMESPACE}
        package = root.find("w:Package", namespace)
        self.assertEqual(package.attrib["UpgradeCode"], UPGRADE_CODE)
        self.assertEqual(package.attrib["Platform"], "x64")
        self.assertIsNotNone(root.find(".//w:MajorUpgrade", namespace))
        self.assertEqual(
            root.find(".//w:Launch", namespace).attrib["Condition"],
            "VersionNT64 >= 1000",
        )
        file_sources = [item.attrib["Source"] for item in root.findall(".//w:File", namespace)]
        self.assertTrue(any(path.endswith("judge.exe") for path in file_sources))
        self.assertTrue(any(path.endswith("problem-studio.exe") for path in file_sources))
        environment = root.find(".//w:Environment", namespace)
        self.assertEqual(environment.attrib["Name"], "PATH")
        self.assertEqual(environment.attrib["Value"], "[INSTALLFOLDER]bin")
        self.assertEqual(environment.attrib["Permanent"], "no")
        self.assertNotIn("AppDataFolder", source)
        self.assertNotIn("RemoveFolder", source)

    def test_windows_standalone_stage_requires_both_exe_launchers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-windows-stage-") as tmp:
            root = Path(tmp)
            archive_path = root / "windows.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                for name in ("judge.exe", "problem-studio.exe"):
                    payload = b"windows-launcher"
                    info = tarfile.TarInfo(f"algorithm-local-judge/bin/{name}")
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))

            app_root = stage_windows_standalone(archive_path, root / "stage")

            self.assertTrue((app_root / "bin" / "judge.exe").is_file())
            self.assertTrue((app_root / "bin" / "problem-studio.exe").is_file())

    def test_msi_version_and_platform_fail_fast(self) -> None:
        self.assertEqual(msi_version("1.2"), "1.2.0")
        with self.assertRaisesRegex(ValueError, "numeric fields"):
            msi_version("1.2.3-beta")
        validate_windows_platform("windows-amd64", "windows-amd64")
        with self.assertRaisesRegex(ValueError, "unsupported Windows installer platform"):
            validate_windows_platform("windows-arm64", "windows-amd64")
        with self.assertRaisesRegex(ValueError, "require a windows-amd64 host"):
            validate_windows_platform("windows-amd64", "linux-amd64")


if __name__ == "__main__":
    unittest.main()
