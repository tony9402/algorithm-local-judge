from __future__ import annotations

import hashlib
import tarfile
import tempfile
import unittest
from pathlib import Path

from judge.core.checksums import write_sha256_sidecar
from judge.core.errors import JudgeError
from scripts.scan_release_artifact import (
    scan_artifact,
    scan_standalone_archive,
    validate_platform_targets,
)
from tests.e2e.pack_fixtures import create_minimal_pack


class ReleaseScannerTest(unittest.TestCase):
    """Tests for local release artifact policy checks."""

    def make_standalone_archive(
        self,
        root: Path,
        *,
        include_notice: bool = True,
        include_static: bool = True,
    ) -> Path:
        """Create a lightweight standalone archive with scanner-required files."""
        app = root / "algorithm-local-judge"
        (app / "bin").mkdir(parents=True)
        (app / "bin" / "judge").write_text("#!/bin/sh\n", encoding="utf-8")
        (app / "README.md").write_text("readme\n", encoding="utf-8")
        if include_notice:
            (app / "THIRD_PARTY_NOTICES.md").write_text("notices\n", encoding="utf-8")
        if include_static:
            static = app / "bin" / "web" / "static"
            (static / "app").mkdir(parents=True)
            (static / "styles").mkdir(parents=True)
            (static / "app.js").write_text("import './app/main.js';\n", encoding="utf-8")
            (static / "styles.css").write_text("@import './styles/base.css';\n", encoding="utf-8")
            (static / "index.html").write_text("<div></div>\n", encoding="utf-8")
            (static / "app" / "main.js").write_text("export {};\n", encoding="utf-8")
            (static / "styles" / "base.css").write_text("body {}\n", encoding="utf-8")

        checksum_lines = []
        for path in sorted(item for item in app.rglob("*") if item.is_file()):
            if path.name == "checksums.txt":
                continue
            checksum_lines.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                f"{path.relative_to(app).as_posix()}"
            )
        (app / "checksums.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

        archive_path = root / "algorithm-local-judge-0.1.0-macos-arm64.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(app, arcname=app.name)
        return archive_path

    def test_standalone_requires_third_party_notice_and_static_assets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-scan-") as tmp:
            root = Path(tmp)
            missing_notice = self.make_standalone_archive(root / "notice", include_notice=False)
            missing_static = self.make_standalone_archive(root / "static", include_static=False)

            with self.assertRaisesRegex(JudgeError, "THIRD_PARTY_NOTICES"):
                scan_standalone_archive(missing_notice)
            with self.assertRaisesRegex(JudgeError, "static"):
                scan_standalone_archive(missing_static)

    def test_standalone_accepts_required_notice_static_and_checksums(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-scan-") as tmp:
            archive_path = self.make_standalone_archive(Path(tmp))

            scan_standalone_archive(archive_path)

    def test_pack_scan_requires_sidecar_checksum(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-pack-scan-") as tmp:
            pack_path = create_minimal_pack(Path(tmp) / "basic-1-macos-arm64.aljpack")

            with self.assertRaisesRegex(JudgeError, "missing checksum sidecar"):
                scan_artifact(pack_path)

            write_sha256_sidecar(pack_path)
            scan_artifact(pack_path)

    def test_platform_targets_only_fail_when_requested(self) -> None:
        artifacts = [Path("dist/packs/basic-1-macos-arm64.aljpack")]

        validate_platform_targets(artifacts, ["macos-arm64"])
        with self.assertRaisesRegex(JudgeError, "linux-amd64"):
            validate_platform_targets(artifacts, ["linux-amd64"])


if __name__ == "__main__":
    unittest.main()
