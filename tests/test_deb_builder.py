"""Debian installer staging contracts."""

from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.build_deb import stage_deb


class DebianInstallerTest(unittest.TestCase):
    def test_stage_contains_nonroot_app_symlink_and_dependency_guidance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-deb-stage-") as tmp:
            root = Path(tmp)
            archive_path = root / "standalone.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                payloads = {
                    "algorithm-local-judge/bin/judge": b"#!/bin/sh\n",
                    "algorithm-local-judge/bin/problem-studio": b"#!/bin/sh\n",
                    "algorithm-local-judge/README.md": b"local judge\n",
                }
                for name, payload in payloads.items():
                    info = tarfile.TarInfo(name)
                    info.mode = 0o755 if "/bin/" in name else 0o644
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))
            stage = root / "stage"
            stage_deb(archive_path, stage, "1.2.3")

            control = (stage / "DEBIAN" / "control").read_text(encoding="utf-8")
            self.assertIn("Version: 1.2.3", control)
            self.assertIn("Recommends: docker.io", control)
            self.assertTrue((stage / "opt" / "algorithm-local-judge" / "bin" / "judge").is_file())
            for name in ("judge", "problem-studio"):
                self.assertTrue((stage / "opt" / "algorithm-local-judge" / "bin" / name).is_file())
                link = stage / "usr" / "bin" / name
                self.assertTrue(link.is_symlink())
                self.assertEqual(
                    link.readlink().as_posix(),
                    f"/opt/algorithm-local-judge/bin/{name}",
                )

    def test_stage_rejects_archive_without_problem_studio_launcher(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-deb-stage-") as tmp:
            root = Path(tmp)
            archive_path = root / "standalone.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                payload = b"#!/bin/sh\n"
                info = tarfile.TarInfo("algorithm-local-judge/bin/judge")
                info.mode = 0o755
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))

            with self.assertRaisesRegex(ValueError, "problem-studio"):
                stage_deb(archive_path, root / "stage", "1.2.3")


if __name__ == "__main__":
    unittest.main()
