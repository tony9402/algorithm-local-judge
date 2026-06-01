"""하위 프로세스 실행 보강 로직이 출력 제한, 파일 제한, 타임아웃 종료를 지키는지 검증하는 테스트 모듈입니다."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from judge.utils.process import DEFAULT_CHILD_STACK_LIMIT_BYTES, run_command_result


class ProcessHardeningTest(unittest.TestCase):
    """프로세스 보강 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_stdout_and_stderr_are_capped(self) -> None:
        """표준 출력 및 표준 오류 제한 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """출력 경로 제한 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """타임아웃 종료 자식 프로세스 그룹 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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

    @unittest.skipIf(os.name == "nt", "stack resource limits are POSIX-specific")
    def test_child_process_stack_soft_limit_is_raised(self) -> None:
        """자식 프로세스 stack soft limit이 가능한 범위 안에서 2048MB까지 올라가는지 검증합니다."""
        import resource

        script = (
            "import resource; "
            "soft, hard = resource.getrlimit(resource.RLIMIT_STACK); "
            "print(f'{soft} {hard}')"
        )

        result = run_command_result([sys.executable, "-c", script], timeout_ms=2000)

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        soft_text, _hard_text = result.stdout.decode("utf-8").strip().split()
        _parent_soft, parent_hard = resource.getrlimit(resource.RLIMIT_STACK)
        expected = DEFAULT_CHILD_STACK_LIMIT_BYTES
        if parent_hard != resource.RLIM_INFINITY:
            expected = min(expected, parent_hard)
        self.assertEqual(int(soft_text), expected)


if __name__ == "__main__":
    unittest.main()
