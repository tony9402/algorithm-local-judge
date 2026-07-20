"""Input bounds, transactional replacement, and release-install integrity contracts."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from alj_core import security_limits
from alj_core.errors import LimitExceededError
from alj_core.utils.fs import transactional_replace_directory
from commons.job_persistence import AtomicJsonFile
from problem_studio.core.editor import save_solution_upload, write_problem_file
from problem_studio.web.schemas import FileWriteRequest, SolutionStressRequest


class IntegrityLimitsTest(unittest.TestCase):
    def test_problem_file_and_schema_reject_oversized_utf8_text(self) -> None:
        text = "가" * security_limits.MAX_SOURCE_TEXT_BYTES
        with self.assertRaises(ValueError):
            FileWriteRequest(content=text)
        with tempfile.TemporaryDirectory(prefix="alj-limit-test-") as tmp:
            workspace = Path(tmp)
            problem = workspace / "problems" / "alpha"
            problem.mkdir(parents=True)
            with self.assertRaises(LimitExceededError):
                write_problem_file(workspace, "alpha", "notes.md", text)

    def test_solution_upload_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-limit-test-") as tmp:
            workspace = Path(tmp)
            problem = workspace / "problems" / "alpha" / "solutions"
            problem.mkdir(parents=True)
            with self.assertRaises(LimitExceededError):
                save_solution_upload(
                    workspace,
                    "alpha",
                    "large.wa.py",
                    b"x" * (security_limits.MAX_SOURCE_UPLOAD_BYTES + 1),
                )
            self.assertEqual(list(problem.iterdir()), [])

    def test_stress_request_caps_duration_cases_and_solution_selection(self) -> None:
        # The request keeps compatibility with the existing API contract for
        # values above the execution cap; the stress core clamps the effective
        # runtime to MAX_STRESS_DURATION_SECONDS before starting a job.
        request = SolutionStressRequest(duration_seconds=301)
        self.assertEqual(request.duration_seconds, 301)
        with self.assertRaises(ValueError):
            SolutionStressRequest(max_cases=security_limits.MAX_STRESS_CASES + 1)
        with self.assertRaises(ValueError):
            SolutionStressRequest(
                solutions=["solutions/a.py"] * (security_limits.MAX_STRESS_SOLUTIONS + 1)
            )

    def test_transactional_directory_replacement_keeps_new_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-transaction-test-") as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "new.txt").write_text("new", encoding="utf-8")
            (target / "old.txt").write_text("old", encoding="utf-8")
            transactional_replace_directory(source, target)
            self.assertEqual((target / "new.txt").read_text(encoding="utf-8"), "new")
            self.assertFalse((target / "old.txt").exists())
            self.assertEqual(list(root.glob(".target.*")), [])

    def test_atomic_json_file_uses_process_lock_sidecar(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-lock-test-") as tmp:
            path = Path(tmp) / "jobs.json"
            store = AtomicJsonFile(path)
            self.assertTrue(store.write({"jobs": []}))
            self.assertEqual(store.read(), {"jobs": []})
            self.assertTrue(store.lock_path.exists())
            if os.name != "nt":
                self.assertEqual(store.lock_path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
