"""Static contracts for the signed macOS/Linux local installer."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_local.sh"


class LocalInstallerTest(unittest.TestCase):
    def _write_fake_release(self, root: Path) -> Path:
        application = root / "payload" / "algorithm-local-judge" / "bin"
        application.mkdir(parents=True)
        for name in ("judge", "problem-studio"):
            launcher = application / name
            launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            launcher.chmod(0o755)
        archive = root / "release.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            output.add(application.parent, arcname="algorithm-local-judge")
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        (root / "release.sha256").write_text(f"{checksum}  release.tar.gz\n", encoding="utf-8")
        (root / "release.sigstore.json").write_text("{}\n", encoding="utf-8")
        return archive

    def _write_fake_commands(self, root: Path) -> Path:
        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        curl = fake_bin / "curl"
        curl.write_text(
            """#!/bin/sh
output=""
while [ "$#" -gt 0 ]; do
    if [ "$1" = "--output" ]; then
        output="$2"
        shift 2
    else
        shift
    fi
done
case "$output" in
    *.sha256) cp "$TEST_RELEASE_SHA256" "$output" ;;
    *.sigstore.json) cp "$TEST_RELEASE_SIGSTORE" "$output" ;;
    *) cp "$TEST_RELEASE_ARCHIVE" "$output" ;;
esac
""",
            encoding="utf-8",
        )
        curl.chmod(0o755)
        cosign = fake_bin / "cosign"
        cosign.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        cosign.chmod(0o755)
        link = fake_bin / "ln"
        link.write_text(
            """#!/bin/sh
if [ "${TEST_FAIL_STUDIO_LINK:-0}" = "1" ]; then
    case "${3:-}" in
        */problem-studio) exit 1 ;;
    esac
fi
exec /bin/ln "$@"
""",
            encoding="utf-8",
        )
        link.chmod(0o755)
        return fake_bin

    def test_shell_syntax_and_dry_run(self) -> None:
        syntax = subprocess.run(
            ["bash", "-n", str(INSTALLER)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        dry_run = subprocess.run(
            ["bash", str(INSTALLER), "--release-tag", "v0.1.0", "--dry-run"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        self.assertIn("Judge local installer dry run", dry_run.stdout)
        self.assertIn("releases/download/v0.1.0", dry_run.stdout)
        self.assertIn("problem-studio", dry_run.stdout)

    def test_installer_requires_checksum_and_sigstore_identity(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn(".sha256", source)
        self.assertIn(".sigstore.json", source)
        self.assertIn("cosign verify-blob", source)
        self.assertIn("--certificate-identity-regexp", source)
        self.assertIn("--release-tag", source)
        self.assertNotIn("releases/latest/download", source)
        self.assertNotIn("--insecure", source)
        self.assertNotIn("--skip-signature", source)

    def test_installer_requires_and_links_both_launchers_with_rollback(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('command_names=("judge" "problem-studio")', source)
        self.assertIn('[[ ! -x "$staged/bin/$command_name" ]]', source)
        self.assertIn("restore_command_links()", source)
        self.assertIn("rollback_install()", source)
        self.assertIn('ln -s "$install_root/bin/$command_name"', source)

    def test_second_link_failure_restores_install_and_both_previous_commands(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-local-installer-") as tmp:
            root = Path(tmp)
            archive = self._write_fake_release(root)
            fake_bin = self._write_fake_commands(root)
            install_root = root / "application"
            install_root.mkdir()
            (install_root / "previous-marker").write_text("old\n", encoding="utf-8")
            bin_dir = root / "commands"
            bin_dir.mkdir()
            judge_link = bin_dir / "judge"
            judge_link.symlink_to("../old/judge")
            studio_command = bin_dir / "problem-studio"
            studio_command.write_text("previous studio\n", encoding="utf-8")

            environment = os.environ.copy()
            environment.update(
                {
                    "ALJ_INSTALL_ROOT": str(install_root),
                    "ALJ_BIN_DIR": str(bin_dir),
                    "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                    "TEST_RELEASE_ARCHIVE": str(archive),
                    "TEST_RELEASE_SHA256": str(root / "release.sha256"),
                    "TEST_RELEASE_SIGSTORE": str(root / "release.sigstore.json"),
                    "ALJ_INSTALL_RELEASE_TAG": "v0.1.0",
                    "TEST_FAIL_STUDIO_LINK": "1",
                }
            )
            result = subprocess.run(
                ["bash", str(INSTALLER)],
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((install_root / "previous-marker").read_text(), "old\n")
            self.assertTrue(judge_link.is_symlink())
            self.assertEqual(judge_link.readlink().as_posix(), "../old/judge")
            self.assertEqual(studio_command.read_text(), "previous studio\n")
            self.assertFalse(Path(f"{install_root}.previous").exists())

    def test_successful_install_exposes_both_commands(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-local-installer-") as tmp:
            root = Path(tmp)
            archive = self._write_fake_release(root)
            fake_bin = self._write_fake_commands(root)
            install_root = root / "application"
            bin_dir = root / "commands"
            environment = os.environ.copy()
            environment.update(
                {
                    "ALJ_INSTALL_ROOT": str(install_root),
                    "ALJ_BIN_DIR": str(bin_dir),
                    "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                    "TEST_RELEASE_ARCHIVE": str(archive),
                    "TEST_RELEASE_SHA256": str(root / "release.sha256"),
                    "TEST_RELEASE_SIGSTORE": str(root / "release.sigstore.json"),
                    "ALJ_INSTALL_RELEASE_TAG": "v0.1.0",
                }
            )

            result = subprocess.run(
                ["bash", str(INSTALLER)],
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("judge", "problem-studio"):
                command = bin_dir / name
                self.assertTrue(command.is_symlink())
                self.assertEqual(command.resolve(), (install_root / "bin" / name).resolve())
                self.assertTrue(os.access(command, os.X_OK))


if __name__ == "__main__":
    unittest.main()
