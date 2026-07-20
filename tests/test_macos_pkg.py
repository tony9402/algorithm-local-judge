"""macOS PKG staging, signing, and notarization contracts."""

from __future__ import annotations

import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_macos_pkg import build_pkg, signing_configuration


def make_archive(root: Path) -> Path:
    payload = root / "payload" / "algorithm-local-judge" / "bin"
    payload.mkdir(parents=True)
    for name in ("judge", "problem-studio"):
        launcher = payload / name
        launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        launcher.chmod(0o755)
    library = payload / "runtime" / "nested" / "fixture.dylib"
    library.parent.mkdir(parents=True)
    library.write_bytes(b"fixture-mach-o-library")
    archive = root / "algorithm-local-judge-0.1.0-macos-arm64.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(root / "payload" / "algorithm-local-judge", arcname="algorithm-local-judge")
    return archive


class MacosPkgTest(unittest.TestCase):
    def test_candidate_pkg_stages_two_launchers_without_claiming_native_signing(self) -> None:
        commands: list[list[str]] = []
        with tempfile.TemporaryDirectory(prefix="alj-macos-pkg-") as tmp:
            root = Path(tmp)
            archive = make_archive(root)

            def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                if command[0] == "pkgbuild":
                    Path(command[-1]).write_bytes(b"candidate-pkg")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch("scripts.build_macos_pkg.require_tool", side_effect=lambda name: name),
                patch("scripts.build_macos_pkg.run_checked", side_effect=fake_run),
            ):
                package, evidence = build_pkg(
                    archive,
                    root / "out",
                    "0.1.0",
                    "macos-arm64",
                    stable=False,
                )

            payload = json.loads(evidence.read_text(encoding="utf-8"))

        pkgbuild = next(command for command in commands if command[0] == "pkgbuild")
        self.assertNotIn("--sign", pkgbuild)
        self.assertEqual(package.name, "algorithm-local-judge-0.1.0-macos-arm64.pkg")
        self.assertEqual(payload["status"], "unconfigured")
        self.assertEqual(payload["artifact"]["name"], package.name)

    def test_stable_fails_closed_when_any_apple_credential_is_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "APPLE_DEVELOPER_ID_INSTALLER"):
            signing_configuration(
                {
                    "APPLE_DEVELOPER_ID_APPLICATION": "Developer ID Application: fixture",
                    "APPLE_NOTARY_PROFILE": "fixture-profile",
                }
            )

    def test_stable_requires_codesign_installer_signature_and_accepted_notarization(self) -> None:
        commands: list[list[str]] = []
        with tempfile.TemporaryDirectory(prefix="alj-macos-pkg-") as tmp:
            root = Path(tmp)
            archive = make_archive(root)

            def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                if command[0] == "pkgbuild":
                    Path(command[-1]).write_bytes(b"signed-notarized-pkg")
                if command[0] == "file":
                    stdout = "Mach-O 64-bit executable"
                elif "notarytool" in command:
                    stdout = '{"id":"notary-fixture","status":"Accepted"}'
                else:
                    stdout = ""
                return subprocess.CompletedProcess(command, 0, stdout, "")

            environment = {
                "APPLE_DEVELOPER_ID_APPLICATION": "Developer ID Application: fixture",
                "APPLE_DEVELOPER_ID_INSTALLER": "Developer ID Installer: fixture",
                "APPLE_NOTARY_PROFILE": "fixture-profile",
            }
            with (
                patch("scripts.build_macos_pkg.require_tool", side_effect=lambda name: name),
                patch("scripts.build_macos_pkg.run_checked", side_effect=fake_run),
            ):
                package, evidence = build_pkg(
                    archive,
                    root / "out",
                    "0.1.0",
                    "macos-arm64",
                    stable=True,
                    environ=environment,
                )
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertTrue(package.is_file())

        self.assertEqual(payload["status"], "verified")
        self.assertEqual(payload["attestation"]["submissionId"], "notary-fixture")
        self.assertEqual(sum(command[0] == "codesign" for command in commands), 6)
        signed = [command[-1] for command in commands if command[:2] == ["codesign", "--force"]]
        self.assertTrue(any(path.endswith("fixture.dylib") for path in signed))
        self.assertTrue(signed[0].endswith("fixture.dylib"))
        pkgbuild = next(command for command in commands if command[0] == "pkgbuild")
        self.assertIn("Developer ID Installer: fixture", pkgbuild)
        self.assertTrue(any("notarytool" in command for command in commands))
        self.assertTrue(any("stapler" in command for command in commands))
        self.assertTrue(any(command[0] == "spctl" for command in commands))

    def test_archive_path_or_link_escape_is_rejected_before_staging(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-macos-pkg-") as tmp:
            root = Path(tmp)
            archive = root / "unsafe.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                member = tarfile.TarInfo("algorithm-local-judge/bin/escape")
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                output.addfile(member)
            with (
                patch("scripts.build_macos_pkg.require_tool", return_value="pkgbuild"),
                self.assertRaisesRegex(ValueError, "unsafe standalone archive"),
            ):
                build_pkg(
                    archive,
                    root / "out",
                    "0.1.0",
                    "macos-arm64",
                    stable=False,
                )


if __name__ == "__main__":
    unittest.main()
