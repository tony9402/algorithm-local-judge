"""Signed APT repository and bootstrap package contracts."""

from __future__ import annotations

import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_apt_repository import build_apt_repository


class AptRepositoryTest(unittest.TestCase):
    def test_candidate_builds_unsigned_metadata_without_fabricated_channel(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-apt-") as tmp:
            root = Path(tmp)
            deb = root / "algorithm-local-judge_0.1.0_amd64.deb"
            deb.write_bytes(b"fixture-deb")
            archive, bootstrap, evidence = build_apt_repository(
                deb,
                root / "out",
                "0.1.0",
                stable=False,
            )
            with tarfile.open(archive, "r:gz") as package:
                names = set(package.getnames())
                packages = (
                    package.extractfile("dists/stable/main/binary-amd64/Packages").read().decode()
                )
            payload = json.loads(evidence.read_text(encoding="utf-8"))

        self.assertIsNone(bootstrap)
        self.assertIn("dists/stable/Release", names)
        self.assertNotIn("dists/stable/InRelease", names)
        self.assertIn(deb.name, packages)
        self.assertEqual(payload["status"], "unconfigured")

    def test_stable_fails_closed_without_real_key_and_channel_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-apt-") as tmp:
            root = Path(tmp)
            deb = root / "algorithm-local-judge_0.1.0_amd64.deb"
            deb.write_bytes(b"fixture-deb")
            with self.assertRaisesRegex(ValueError, "ALJ_APT_GPG_KEY_ID"):
                build_apt_repository(deb, root / "out", "0.1.0", stable=True)

    def test_stable_signs_release_and_builds_keyring_bootstrap(self) -> None:
        commands: list[list[str]] = []
        with tempfile.TemporaryDirectory(prefix="alj-apt-") as tmp:
            root = Path(tmp)
            deb = root / "algorithm-local-judge_0.1.0_amd64.deb"
            deb.write_bytes(b"fixture-deb")
            public_key = root / "archive-keyring.gpg"
            public_key.write_bytes(b"fixture-public-key")

            def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                if "--fingerprint" in command:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        "fpr:::::::::0123456789ABCDEF0123456789ABCDEF01234567:\n",
                        "",
                    )
                if "--output" in command:
                    Path(command[command.index("--output") + 1]).write_text(
                        "fixture-signature", encoding="utf-8"
                    )
                if command[0] == "dpkg-deb":
                    Path(command[-1]).write_bytes(b"bootstrap-deb")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch("scripts.build_apt_repository.require_tool", side_effect=lambda name: name),
                patch("scripts.build_apt_repository.run_checked", side_effect=fake_run),
            ):
                archive, bootstrap, evidence = build_apt_repository(
                    deb,
                    root / "out",
                    "0.1.0",
                    stable=True,
                    gpg_key_id="fixture-key",
                    repository_url="https://packages.example.test/algorithm-local-judge",
                    public_key=public_key,
                )
            with tarfile.open(archive, "r:gz") as package:
                names = set(package.getnames())
            payload = json.loads(evidence.read_text(encoding="utf-8"))

        self.assertIsNotNone(bootstrap)
        self.assertTrue(bootstrap.name.startswith("algorithm-local-judge-archive-keyring_"))
        self.assertIn("dists/stable/InRelease", names)
        self.assertIn("dists/stable/Release.gpg", names)
        self.assertEqual(payload["status"], "verified")
        self.assertEqual(
            payload["attestation"]["keyFingerprint"],
            "0123456789ABCDEF0123456789ABCDEF01234567",
        )
        self.assertTrue(any("--verify" in command for command in commands))

    def test_stable_rejects_bootstrap_key_that_does_not_match_release_signature(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-apt-") as tmp:
            root = Path(tmp)
            deb = root / "algorithm-local-judge_0.1.0_amd64.deb"
            deb.write_bytes(b"fixture-deb")
            public_key = root / "archive-keyring.gpg"
            public_key.write_bytes(b"wrong-public-key")

            def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
                if "--fingerprint" in command:
                    fingerprint = (
                        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
                        if "--show-keys" in command
                        else "0123456789ABCDEF0123456789ABCDEF01234567"
                    )
                    return subprocess.CompletedProcess(
                        command, 0, f"fpr:::::::::{fingerprint}:\n", ""
                    )
                if "--output" in command:
                    Path(command[command.index("--output") + 1]).write_text(
                        "fixture-signature", encoding="utf-8"
                    )
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch("scripts.build_apt_repository.require_tool", side_effect=lambda name: name),
                patch("scripts.build_apt_repository.run_checked", side_effect=fake_run),
                self.assertRaisesRegex(ValueError, "does not match"),
            ):
                build_apt_repository(
                    deb,
                    root / "out",
                    "0.1.0",
                    stable=True,
                    gpg_key_id="fixture-key",
                    repository_url="https://packages.example.test/algorithm-local-judge",
                    public_key=public_key,
                )

    def test_bootstrap_rejects_non_https_repository_url(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-apt-") as tmp:
            root = Path(tmp)
            deb = root / "algorithm-local-judge_0.1.0_amd64.deb"
            deb.write_bytes(b"fixture-deb")
            key = root / "key.gpg"
            key.write_bytes(b"key")
            with self.assertRaisesRegex(ValueError, "absolute HTTPS"):
                with patch("scripts.build_apt_repository.require_tool", return_value="dpkg-deb"):
                    build_apt_repository(
                        deb,
                        root / "out",
                        "0.1.0",
                        stable=False,
                        repository_url="http://packages.example.test/alj",
                        public_key=key,
                    )


if __name__ == "__main__":
    unittest.main()
