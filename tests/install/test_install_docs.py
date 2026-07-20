"""README installation documentation and native channel publication contracts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from judge.core.errors import JudgeError
from scripts.verify_install_docs import (
    REQUIRED_OS,
    parse_blocks,
    validate_install_docs,
)

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
CHANNELS = ROOT / "packaging" / "install-channels.json"


class InstallDocumentationTest(unittest.TestCase):
    def test_current_unpublished_blocks_are_structured_without_fake_commands(self) -> None:
        validate_install_docs(README, CHANNELS)
        blocks = parse_blocks(README.read_text(encoding="utf-8"))
        self.assertEqual(set(blocks), set(REQUIRED_OS))
        for block in blocks.values():
            self.assertEqual(block.status, "unpublished")
            self.assertEqual(block.language, "text")
            self.assertGreaterEqual(len(block.lines), 2)
            self.assertLessEqual(len(block.lines), 3)

    def test_stable_gate_fails_while_any_channel_is_unpublished(self) -> None:
        with self.assertRaisesRegex(JudgeError, "stable install gate is blocked"):
            validate_install_docs(README, CHANNELS, stable=True)

    def test_unpublished_windows_block_must_not_expose_unverified_package_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-install-docs-") as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(
                README.read_text(encoding="utf-8") + "\nwinget install Unverified.Product\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(JudgeError, "unverified windows install channel"):
                validate_install_docs(readme, CHANNELS)

    def test_published_commands_reject_hidden_python_uv_git_or_cosign_prerequisite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-install-docs-") as tmp:
            root = Path(tmp)
            text = (
                README.read_text(encoding="utf-8")
                .replace(
                    "<!-- alj-install:start os=macos status=unpublished -->",
                    "<!-- alj-install:start os=macos status=published -->",
                )
                .replace(
                    "```text\n상태: 미공개 — Apple Silicon과 Intel용 서명·공증 설치 채널을 검증 중입니다.\n"
                    "명령: stable 공급망 및 clean-OS gate 통과 후 이 블록에 2~3개 명령을 게시합니다.\n```",
                    "```bash\nbrew install cosign\njudge setup --yes\n```",
                    1,
                )
            )
            readme = root / "README.md"
            readme.write_text(text, encoding="utf-8")
            channels = json.loads(CHANNELS.read_text(encoding="utf-8"))
            channels["channels"]["macos"].update(
                {
                    "status": "published",
                    "installCommands": ["brew install cosign", "judge setup --yes"],
                }
            )
            channel_path = root / "channels.json"
            channel_path.write_text(json.dumps(channels), encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "hidden prerequisite"):
                validate_install_docs(readme, channel_path)

    def test_published_commands_reject_placeholder_or_latest_channel(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-install-docs-") as tmp:
            root = Path(tmp)
            text = (
                README.read_text(encoding="utf-8")
                .replace(
                    "<!-- alj-install:start os=macos status=unpublished -->",
                    "<!-- alj-install:start os=macos status=published -->",
                )
                .replace(
                    "```text\n상태: 미공개 — Apple Silicon과 Intel용 서명·공증 설치 채널을 검증 중입니다.\n"
                    "명령: stable 공급망 및 clean-OS gate 통과 후 이 블록에 2~3개 명령을 게시합니다.\n```",
                    "```bash\nbrew install <tap>/algorithm-local-judge/latest\njudge setup --yes\n```",
                    1,
                )
            )
            readme = root / "README.md"
            readme.write_text(text, encoding="utf-8")
            channels = json.loads(CHANNELS.read_text(encoding="utf-8"))
            channels["channels"]["macos"].update(
                {
                    "status": "published",
                    "installCommands": [
                        "brew install <tap>/algorithm-local-judge/latest",
                        "judge setup --yes",
                    ],
                }
            )
            channel_path = root / "channels.json"
            channel_path.write_text(json.dumps(channels), encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "placeholder/channel"):
                validate_install_docs(readme, channel_path)


class InstallWorkflowContractTest(unittest.TestCase):
    def test_matrix_defines_all_clean_os_targets_and_lifecycle_gate(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "install-smoke.yml").read_text(
            encoding="utf-8"
        )
        for value in (
            "macos-arm64",
            "macos-amd64",
            "ubuntu-amd64",
            "debian-amd64",
            "fedora-amd64",
            "windows-amd64",
        ):
            self.assertIn(value, workflow)
        self.assertIn("verify_install_docs.py --stable", workflow)
        self.assertIn("run_clean_os_contract.py", workflow)
        self.assertIn("source-install:", workflow)
        self.assertIn("install.sh --skip-checks", workflow)
        self.assertIn("install.ps1 -SkipChecks", workflow)
        self.assertIn("source:", workflow)
        self.assertNotIn("continue-on-error: true", workflow)

    def test_release_stable_publish_requires_install_docs_gate(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        docs_gate = workflow.index("verify_install_docs.py --stable")
        upload = workflow.index("gh release upload")
        self.assertLess(docs_gate, upload)


if __name__ == "__main__":
    unittest.main()
