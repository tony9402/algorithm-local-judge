from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from judge.utils.process import run_command_result


class ProcessHardeningTest(unittest.TestCase):
    """Tests for subprocess timeout and output cap behavior."""

    def test_stdout_and_stderr_are_capped(self) -> None:
        script = "import sys; sys.stdout.write('o' * 200); sys.stderr.write('e' * 200)"

        result = run_command_result(
            [sys.executable, "-c", script],
            timeout_ms=2000,
            stdout_limit_bytes=80,
            stderr_limit_bytes=80,
        )

        self.assertEqual(result.returncode, 0)
        self.assertLessEqual(len(result.stdout), 80)
        self.assertLessEqual(len(result.stderr), 80)
        self.assertTrue(result.stdout_truncated)
        self.assertTrue(result.stderr_truncated)
        self.assertIn(b"stdout truncated", result.stdout)
        self.assertIn(b"stderr truncated", result.stderr)

    def test_output_path_is_capped(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-process-output-") as tmp:
            output = Path(tmp) / "actual.out"
            result = run_command_result(
                [sys.executable, "-c", "import sys; sys.stdout.write('x' * 200)"],
                timeout_ms=2000,
                output_path=output,
                output_limit_bytes=64,
                stderr_limit_bytes=200,
            )

            self.assertEqual(result.returncode, 0)
            self.assertTrue(result.output_truncated)
            self.assertLessEqual(output.stat().st_size, 64)
            self.assertIn(b"actual output truncated to 64 bytes", result.stderr)

    @unittest.skipIf(os.name == "nt", "process group cleanup is POSIX-specific")
    def test_timeout_kills_child_process_group(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-process-group-") as tmp:
            marker = Path(tmp) / "child-survived.txt"
            script = (
                "import pathlib, subprocess, sys, time; "
                "marker = pathlib.Path(sys.argv[1]); "
                "subprocess.Popen([sys.executable, '-c', "
                '"import pathlib, sys, time; '
                "time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('survived')\", "
                "str(marker)]); "
                "time.sleep(5)"
            )

            result = run_command_result(
                [sys.executable, "-c", script, str(marker)],
                timeout_ms=100,
            )
            time.sleep(1.0)

            self.assertEqual(result.returncode, 124)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
