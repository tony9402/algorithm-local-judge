"""배포 패키지 smoke fixture와 실패 진단 계약을 검증합니다."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.smoke_judge_web_package import (
    SMOKE_COMPILE_TIMEOUT_MS,
    create_smoke_problem,
    run_command,
)
from tests.e2e.helpers import ROOT


class PackageSmokeContractTest(unittest.TestCase):
    """느린 Linux runner에서도 패키지 smoke가 안정적으로 진단되는지 확인합니다."""

    def test_smoke_problem_allows_cold_toolchain_compilation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-package-smoke-contract-") as tmp:
            source_root = Path(tmp) / "source"
            source_root.mkdir()
            problem_root = create_smoke_problem(source_root, ROOT)
            metadata = json.loads((problem_root / "problem.json").read_text(encoding="utf-8"))

        self.assertGreaterEqual(SMOKE_COMPILE_TIMEOUT_MS, 30_000)
        self.assertEqual(metadata["limits"]["compileTimeoutMs"], SMOKE_COMPILE_TIMEOUT_MS)

    def test_captured_command_failure_includes_process_output(self) -> None:
        failure = subprocess.CalledProcessError(
            7,
            ["judge", "pack", "build"],
            output="captured stdout",
            stderr="captured stderr",
        )
        with (
            patch("scripts.smoke_judge_web_package.subprocess.run", side_effect=failure),
            self.assertRaises(RuntimeError) as raised,
        ):
            run_command(["judge", "pack", "build"], ROOT, capture=True)

        message = str(raised.exception)
        self.assertIn("exit: 7", message)
        self.assertIn("captured stdout", message)
        self.assertIn("captured stderr", message)


if __name__ == "__main__":
    unittest.main()
