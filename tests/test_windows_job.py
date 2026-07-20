"""Platform-neutral contracts for the Windows Job Object adapter."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from alj_core.utils.windows_job import WindowsJob, create_windows_job


class WindowsJobContractTest(unittest.TestCase):
    def test_factory_is_a_noop_outside_windows(self) -> None:
        if os.name == "nt":
            self.skipTest("POSIX-only no-op contract")
        self.assertIsNone(create_windows_job(1024))

    def test_known_windows_memory_failure_is_classified(self) -> None:
        job = object.__new__(WindowsJob)
        job.memory_limit_bytes = 1024
        with patch.object(job, "_drain_memory_limit_messages", return_value=False):
            self.assertTrue(job.memory_limit_exceeded(0xC0000017, 900))

    def test_memory_message_is_classified_without_exit_code_guessing(self) -> None:
        job = object.__new__(WindowsJob)
        job.memory_limit_bytes = 1024
        with patch.object(job, "_drain_memory_limit_messages", return_value=True):
            self.assertTrue(job.memory_limit_exceeded(0, 900))

    def test_no_configured_limit_never_reports_memory_limit(self) -> None:
        job = object.__new__(WindowsJob)
        job.memory_limit_bytes = None
        self.assertFalse(job.memory_limit_exceeded(0xC0000017, 4096))


if __name__ == "__main__":
    unittest.main()
