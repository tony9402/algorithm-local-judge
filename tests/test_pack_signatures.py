"""Problem-pack Sigstore policy and Cosign command contracts."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from judge.core.errors import JudgeError
from judge.core.pack_signatures import (
    github_workflow_identity_pattern,
    sign_pack,
    verify_pack_signature,
)


class PackSignatureTest(unittest.TestCase):
    def test_github_identity_is_anchored_to_repository_tag_workflows(self) -> None:
        pattern = github_workflow_identity_pattern("owner/repository")
        self.assertEqual(
            pattern,
            r"^https://github\.com/owner/repository/\.github/workflows/[^@]+@refs/tags/.+$",
        )

    def test_verify_uses_repository_identity_and_github_issuer(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-signature-test-") as tmp:
            archive = Path(tmp) / "basic.aljpack"
            bundle = Path(tmp) / "basic.aljpack.sigstore.json"
            archive.write_bytes(b"pack")
            bundle.write_text("{}", encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, stdout="Verified OK", stderr="")
            with (
                patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True),
                patch("judge.core.pack_signatures.shutil.which", return_value="/usr/bin/cosign"),
                patch("judge.core.pack_signatures.subprocess.run", return_value=completed) as run,
            ):
                result = verify_pack_signature(archive, bundle, "owner/repository")

        command = run.call_args.args[0]
        self.assertIn("--certificate-identity-regexp", command)
        self.assertIn("owner/repository", result["signatureIdentity"])
        self.assertEqual(result["signatureIssuer"], "https://token.actions.githubusercontent.com")
        self.assertTrue(result["signatureVerified"])

    def test_verify_supports_explicit_offline_public_key_policy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-signature-key-test-") as tmp:
            archive = Path(tmp) / "basic.aljpack"
            bundle = Path(tmp) / "basic.sigstore.json"
            archive.write_bytes(b"pack")
            bundle.write_text("{}", encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, stdout="Verified OK", stderr="")
            with (
                patch.dict(
                    os.environ,
                    {"ALJ_PACK_SIGNATURE_PUBLIC_KEY": "/keys/publisher.pub"},
                    clear=True,
                ),
                patch("judge.core.pack_signatures.shutil.which", return_value="cosign"),
                patch("judge.core.pack_signatures.subprocess.run", return_value=completed) as run,
            ):
                result = verify_pack_signature(archive, bundle, "owner/repository")

        command = run.call_args.args[0]
        self.assertEqual(command[-2:], ["--key", "/keys/publisher.pub"])
        self.assertEqual(result["signaturePublicKey"], "/keys/publisher.pub")
        self.assertIsNone(result["signatureIdentity"])

    def test_missing_cosign_has_actionable_install_message(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-signature-missing-test-") as tmp:
            archive = Path(tmp) / "basic.aljpack"
            bundle = Path(tmp) / "basic.sigstore.json"
            archive.write_bytes(b"pack")
            bundle.write_text("{}", encoding="utf-8")
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("judge.core.pack_signatures.shutil.which", return_value=None),
                self.assertRaisesRegex(JudgeError, "brew install cosign"),
            ):
                verify_pack_signature(archive, bundle, "owner/repository")

    def test_sign_pack_creates_default_bundle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-signature-sign-test-") as tmp:
            archive = Path(tmp) / "basic.aljpack"
            archive.write_bytes(b"pack")

            def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
                bundle = Path(command[command.index("--bundle") + 1])
                bundle.write_text("{}", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with (
                patch("judge.core.pack_signatures.shutil.which", return_value="cosign"),
                patch("judge.core.pack_signatures.subprocess.run", side_effect=fake_run),
            ):
                bundle = sign_pack(archive)

            self.assertEqual(bundle.name, "basic.aljpack.sigstore.json")
            self.assertTrue(bundle.exists())


if __name__ == "__main__":
    unittest.main()
