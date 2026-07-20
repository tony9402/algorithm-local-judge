"""Clean-OS install lifecycle fail-closed and ordering contracts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from judge.core.errors import JudgeError
from tests.install.run_clean_os_contract import (
    assert_versions,
    load_channel,
    run_lifecycle,
)

ROOT = Path(__file__).resolve().parents[2]
CHANNELS = ROOT / "packaging" / "install-channels.json"


def published_fixture(root: Path) -> Path:
    channel = {
        "status": "published",
        "smokeInstallCommands": ["install-n-minus-one"],
        "upgradeCommand": "upgrade-current",
        "rollbackCommand": "rollback-n-minus-one",
        "uninstallCommand": "uninstall-product",
        "releaseVersion": "2.0.0",
        "rollbackVersion": "1.0.0",
        "sampleProblem": "smoke",
        "samples": {
            "cpp": "int main() {}",
            "python": "print(1)",
            "pypy": "print(1)",
            "java": "class Main {}",
        },
    }
    path = root / "channels.json"
    path.write_text(
        json.dumps({"schemaVersion": 1, "channels": {"macos": channel}}),
        encoding="utf-8",
    )
    return path


class CleanOsContractTest(unittest.TestCase):
    def test_unpublished_channel_fails_before_any_install_command(self) -> None:
        with self.assertRaisesRegex(JudgeError, "no install command was executed"):
            load_channel(CHANNELS, "macos-arm64")

    def test_two_launcher_versions_are_checked(self) -> None:
        environment = {"PATH": ""}
        with patch(
            "tests.install.run_clean_os_contract.run_command",
            side_effect=["judge 1.2.3\n", "problem-studio 1.2.3\n"],
        ) as run:
            assert_versions(environment, "1.2.3")

        self.assertEqual(
            run.call_args_list,
            [
                call(["judge", "--version"], environment),
                call(["problem-studio", "--version"], environment),
            ],
        )

    def test_lifecycle_orders_setup_ready_languages_upgrade_rollback_uninstall(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-clean-os-contract-") as tmp:
            root = Path(tmp)
            channel_path = published_fixture(root)
            with (
                patch("tests.install.run_clean_os_contract.run_shell") as shell,
                patch("tests.install.run_clean_os_contract.run_command") as command,
                patch("tests.install.run_clean_os_contract.assert_versions") as versions,
                patch("tests.install.run_clean_os_contract.verify_readyz") as readyz,
                patch("tests.install.run_clean_os_contract.verify_language_samples") as languages,
                patch("tests.install.run_clean_os_contract.shutil.which", return_value=None),
            ):
                run_lifecycle("macos-arm64", channel_path, root / "work")

            self.assertEqual(
                [item.args[0] for item in shell.call_args_list],
                [
                    "install-n-minus-one",
                    "upgrade-current",
                    "rollback-n-minus-one",
                    "uninstall-product",
                ],
            )
            self.assertEqual(
                [item.args[1] for item in versions.call_args_list],
                ["1.0.0", "2.0.0", "1.0.0"],
            )
            self.assertEqual(
                command.call_args_list[0].args[0], ["judge", "setup", "--yes", "--no-web"]
            )
            readyz.assert_called_once()
            languages.assert_called_once()


if __name__ == "__main__":
    unittest.main()
