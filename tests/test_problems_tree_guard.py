"""Regression tests for the problems-tree immutability guard."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_with_problems_guard
from scripts.problems_tree_guard import (
    capture_tree,
    changed_paths,
    verify_snapshot,
    write_snapshot,
)


class ProblemsTreeGuardTest(unittest.TestCase):
    def test_guard_script_runs_directly_from_repository_root(self) -> None:
        root_directory = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="alj-problems-direct-guard-") as tmp:
            problems = Path(tmp) / "problems"
            problems.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_with_problems_guard.py",
                    "--root",
                    str(problems),
                    "--",
                    sys.executable,
                    "-c",
                    "pass",
                ],
                cwd=root_directory,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified no additions", result.stdout)

    def test_unchanged_tree_verifies(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-problems-guard-") as tmp:
            root = Path(tmp) / "problems"
            snapshot = Path(tmp) / "snapshot.json"
            (root / "01").mkdir(parents=True)
            (root / "01" / "problem.json").write_text("{}\n", encoding="utf-8")
            write_snapshot(root, snapshot)
            self.assertEqual(verify_snapshot(root, snapshot), [])

    def test_add_modify_delete_and_symlink_target_are_detected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-problems-guard-change-") as tmp:
            root = Path(tmp) / "problems"
            (root / "01").mkdir(parents=True)
            kept = root / "01" / "kept.txt"
            removed = root / "01" / "removed.txt"
            link = root / "current"
            kept.write_text("before\n", encoding="utf-8")
            removed.write_text("remove\n", encoding="utf-8")
            link.symlink_to("01")
            before = capture_tree(root)

            kept.write_text("after\n", encoding="utf-8")
            removed.unlink()
            (root / "01" / "added.txt").write_text("add\n", encoding="utf-8")
            link.unlink()
            link.symlink_to("02")

            self.assertEqual(
                changed_paths(before, capture_tree(root)),
                ["01/added.txt", "01/kept.txt", "01/removed.txt", "current"],
            )

    def test_nested_git_metadata_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-problems-guard-git-") as tmp:
            root = Path(tmp) / "problems"
            git_file = root / "package" / ".git" / "index"
            git_file.parent.mkdir(parents=True)
            git_file.write_text("before", encoding="utf-8")
            before = capture_tree(root)
            git_file.write_text("after", encoding="utf-8")
            self.assertEqual(changed_paths(before, capture_tree(root)), [])

    def test_guarded_command_returns_distinct_failure_when_tree_changes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-problems-command-guard-") as tmp:
            root = Path(tmp) / "problems"
            target = root / "01" / "problem.json"
            target.parent.mkdir(parents=True)
            target.write_text("before\n", encoding="utf-8")

            command = [
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(target)!r}).write_text('after')",
            ]
            with patch(
                "scripts.run_with_problems_guard.parse_args",
                return_value=type("Args", (), {"root": root, "command": command})(),
            ):
                self.assertEqual(run_with_problems_guard.main(), 86)


if __name__ == "__main__":
    unittest.main()
