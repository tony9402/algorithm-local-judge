"""macOS/Linux source-checkout installation and documentation contracts."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.verify_install_docs import (
    EXPECTED_INSTALL_COMMANDS,
    InstallDocsError,
    parse_install_commands,
    parse_linux_install_commands,
    validate_install_docs,
)

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
INSTALL_GUIDE = ROOT / "INSTALL.md"
INSTALLER = ROOT / "install.sh"


class InstallDocumentationTest(unittest.TestCase):
    def test_macos_and_linux_install_documentation_is_consistent(self) -> None:
        validate_install_docs(README, INSTALL_GUIDE, INSTALLER)
        text = README.read_text(encoding="utf-8")
        self.assertEqual(parse_linux_install_commands(text), EXPECTED_INSTALL_COMMANDS)
        self.assertEqual(parse_install_commands(text, "macos"), EXPECTED_INSTALL_COMMANDS)

    def test_second_os_install_block_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-install-docs-") as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(
                README.read_text(encoding="utf-8")
                + "\n<!-- alj-install:start os=linux -->\n```bash\n./install.sh\n```\n"
                + "<!-- alj-install:end os=linux -->\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(InstallDocsError, "exactly one Linux install block"):
                validate_install_docs(readme, INSTALL_GUIDE, INSTALLER)

    def test_unsupported_windows_install_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-install-docs-") as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(
                README.read_text(encoding="utf-8") + "\n```powershell\n.\\install.ps1\n```\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(InstallDocsError, "unsupported Windows install command"):
                validate_install_docs(readme, INSTALL_GUIDE, INSTALLER)


class UnixInstallerTest(unittest.TestCase):
    def test_shell_syntax_and_help(self) -> None:
        syntax = subprocess.run(
            ["bash", "-n", str(INSTALLER)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        help_result = subprocess.run(
            ["bash", str(INSTALLER), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("macOS", help_result.stdout)
        self.assertIn("Linux", help_result.stdout)

    def test_unsupported_host_fails_before_installing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-fake-host-") as tmp:
            fake_bin = Path(tmp)
            uname = fake_bin / "uname"
            uname.write_text("#!/bin/sh\necho FreeBSD\n", encoding="utf-8")
            uname.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            result = subprocess.run(
                ["bash", str(INSTALLER), "--skip-checks"],
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("macOS와 Linux만 지원", result.stderr)

    def test_macos_uv_install_uses_native_default_runtime_and_global_commands(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-macos-install-") as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            (fake_bin / "uname").write_text("#!/bin/sh\necho Darwin\n", encoding="utf-8")
            python = fake_bin / "python-custom"
            python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            uv = fake_bin / "uv"
            uv.write_text(
                "#!/bin/sh\n"
                'mkdir -p "$TEST_INSTALL_DIR/bin"\n'
                "for name in judge problem-studio; do\n"
                "  printf '#!/bin/sh\\nexit 0\\n' > \"$TEST_INSTALL_DIR/bin/$name\"\n"
                '  chmod +x "$TEST_INSTALL_DIR/bin/$name"\n'
                "done\n",
                encoding="utf-8",
            )
            for command in (fake_bin / "uname", python, uv):
                command.chmod(0o755)

            home = root / "home"
            install_dir = (
                home / "Library" / "Application Support" / "algorithm-local-judge" / "runtime"
            )
            command_dir = home / ".local" / "bin"
            profile = home / ".zshrc"
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                    "HOME": str(home),
                    "SHELL": "/bin/zsh",
                    "ALJ_SHELL_PROFILE": str(profile),
                    "TEST_INSTALL_DIR": str(install_dir),
                }
            )
            result = subprocess.run(
                [
                    "bash",
                    str(INSTALLER),
                    "--python",
                    str(python),
                    "--skip-checks",
                ],
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((install_dir / ".algorithm-local-judge-runtime").is_file())
            for name in ("judge", "problem-studio"):
                command_path = command_dir / name
                self.assertTrue(command_path.is_symlink())
                self.assertEqual(command_path.resolve(), (install_dir / "bin" / name).resolve())
            self.assertIn(
                f"export PATH={command_dir.resolve()}:$PATH", profile.read_text(encoding="utf-8")
            )

    def test_linux_uv_install_creates_global_commands_and_registers_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-linux-install-") as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            (fake_bin / "uname").write_text("#!/bin/sh\necho Linux\n", encoding="utf-8")
            python = fake_bin / "python-custom"
            python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            uv = fake_bin / "uv"
            uv.write_text(
                "#!/bin/sh\n"
                'printf \'%s\\n\' "$@" > "$TEST_UV_ARGS"\n'
                'mkdir -p "$TEST_INSTALL_DIR/bin"\n'
                "for name in judge problem-studio; do\n"
                "  printf '#!/bin/sh\\nexit 0\\n' > \"$TEST_INSTALL_DIR/bin/$name\"\n"
                '  chmod +x "$TEST_INSTALL_DIR/bin/$name"\n'
                "done\n",
                encoding="utf-8",
            )
            for command in (fake_bin / "uname", python, uv):
                command.chmod(0o755)
            install_dir = (root / "runtime").resolve()
            command_dir = (root / "commands").resolve()
            profile = (root / "profile").resolve()
            uv_args = root / "uv-args.txt"
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                    "HOME": str(root / "home"),
                    "SHELL": "/bin/bash",
                    "ALJ_SHELL_PROFILE": str(profile),
                    "TEST_UV_ARGS": str(uv_args),
                    "TEST_INSTALL_DIR": str(install_dir),
                }
            )
            command = [
                "bash",
                str(INSTALLER),
                "--python",
                str(python),
                "--install-dir",
                str(install_dir),
                "--bin-dir",
                str(command_dir),
                "--skip-checks",
            ]
            result = subprocess.run(
                command, text=True, capture_output=True, check=False, env=environment
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = uv_args.read_text(encoding="utf-8").splitlines()
            self.assertEqual(arguments[arguments.index("--python") + 1], str(python))
            self.assertIn("--no-editable", arguments)
            self.assertTrue((install_dir / ".algorithm-local-judge-runtime").is_file())
            self.assertTrue((install_dir / "testlib.h").is_file())
            for name in ("judge", "problem-studio"):
                command_path = command_dir / name
                self.assertTrue(command_path.is_symlink())
                self.assertEqual(command_path.resolve(), (install_dir / "bin" / name).resolve())

            path_line = f"export PATH={command_dir}:$PATH"
            self.assertIn(path_line, profile.read_text(encoding="utf-8"))
            direct_environment = environment | {
                "PATH": f"{command_dir}{os.pathsep}{environment['PATH']}"
            }
            direct = subprocess.run(
                ["judge", "--version"],
                text=True,
                capture_output=True,
                check=False,
                env=direct_environment,
            )
            self.assertEqual(direct.returncode, 0, direct.stderr)

            second = subprocess.run(
                command, text=True, capture_output=True, check=False, env=environment
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(profile.read_text(encoding="utf-8").count(path_line), 1)

    def test_piped_installer_bootstraps_the_requested_github_ref(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-curl-bootstrap-") as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            (fake_bin / "uname").write_text("#!/bin/sh\necho Linux\n", encoding="utf-8")
            child_installer = root / "child-install.sh"
            child_installer.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$TEST_CHILD_ARGS\"\n",
                encoding="utf-8",
            )
            git = fake_bin / "git"
            git.write_text(
                "#!/bin/sh\n"
                'printf \'%s\\n\' "$@" > "$TEST_GIT_ARGS"\n'
                "destination=\n"
                'for argument in "$@"; do destination="$argument"; done\n'
                'mkdir -p "$destination"\n'
                'cp "$TEST_CHILD_INSTALLER" "$destination/install.sh"\n'
                'chmod +x "$destination/install.sh"\n'
                'printf \'%s\\n\' "$destination" > "$TEST_BOOTSTRAP_DIR"\n',
                encoding="utf-8",
            )
            for command in (fake_bin / "uname", git, child_installer):
                command.chmod(0o755)

            git_args = root / "git-args.txt"
            child_args = root / "child-args.txt"
            bootstrap_dir = root / "bootstrap-dir.txt"
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                    "HOME": str(root / "home"),
                    "ALJ_INSTALL_REPOSITORY": "owner/project",
                    "ALJ_INSTALL_REF": "v1.2.3",
                    "TEST_GIT_ARGS": str(git_args),
                    "TEST_CHILD_ARGS": str(child_args),
                    "TEST_CHILD_INSTALLER": str(child_installer),
                    "TEST_BOOTSTRAP_DIR": str(bootstrap_dir),
                }
            )
            result = subprocess.run(
                ["bash", "-s", "--", "--skip-checks", "--bin-dir", str(root / "commands")],
                input=INSTALLER.read_text(encoding="utf-8"),
                text=True,
                capture_output=True,
                check=False,
                cwd=root,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            clone_arguments = git_args.read_text(encoding="utf-8").splitlines()
            self.assertIn("--branch", clone_arguments)
            self.assertEqual(clone_arguments[clone_arguments.index("--branch") + 1], "v1.2.3")
            self.assertIn("https://github.com/owner/project.git", clone_arguments)
            self.assertEqual(
                child_args.read_text(encoding="utf-8").splitlines(),
                ["--skip-checks", "--bin-dir", str(root / "commands")],
            )
            temporary_checkout = Path(bootstrap_dir.read_text(encoding="utf-8").strip())
            self.assertFalse(temporary_checkout.exists())

    def test_linux_installer_does_not_overwrite_an_existing_command(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-command-collision-") as tmp:
            root = Path(tmp)
            fake_bin = root / "fake-bin"
            command_dir = root / "commands"
            fake_bin.mkdir()
            command_dir.mkdir()
            (fake_bin / "uname").write_text("#!/bin/sh\necho Linux\n", encoding="utf-8")
            (fake_bin / "uname").chmod(0o755)
            existing = command_dir / "judge"
            existing.write_text("existing command\n", encoding="utf-8")
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                    "HOME": str(root / "home"),
                }
            )
            install_dir = root / "runtime"
            result = subprocess.run(
                [
                    "bash",
                    str(INSTALLER),
                    "--install-dir",
                    str(install_dir),
                    "--bin-dir",
                    str(command_dir),
                    "--skip-checks",
                ],
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("기존 명령을 덮어쓰지 않습니다", result.stderr)
            self.assertEqual(existing.read_text(encoding="utf-8"), "existing command\n")
            self.assertFalse(install_dir.exists())

    def test_windows_installer_is_not_part_of_supported_root_install_flow(self) -> None:
        self.assertFalse((ROOT / "install.ps1").exists())


class InstallWorkflowContractTest(unittest.TestCase):
    def test_install_smoke_runs_the_macos_and_linux_checkout_flow(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "install-smoke.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("runner: ubuntu-latest", workflow)
        self.assertIn("runner: macos-15", workflow)
        self.assertIn("runs-on: ${{ matrix.runner }}", workflow)
        self.assertIn("./install.sh --skip-checks", workflow)
        self.assertIn("python scripts/verify_install_docs.py", workflow)
        self.assertIn("ALJ_INSTALL_DIR:", workflow)
        self.assertIn("ALJ_BIN_DIR:", workflow)
        self.assertIn("judge --version", workflow)
        self.assertIn("problem-studio --version", workflow)
        self.assertIn("judge was installed in editable mode", workflow)
        self.assertNotIn("./.venv/bin/", workflow)
        self.assertNotIn("windows", workflow.lower())
        self.assertNotIn("install.ps1", workflow)
        self.assertNotIn("continue-on-error: true", workflow)

    def test_release_checks_install_docs_before_upload(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        docs_gate = workflow.index("verify_install_docs.py")
        upload = workflow.index("gh release upload")
        self.assertLess(docs_gate, upload)


if __name__ == "__main__":
    unittest.main()
