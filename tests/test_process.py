"""하위 프로세스 실행 보강 로직이 출력 제한, 파일 제한, 타임아웃 종료를 지키는지 검증하는 테스트 모듈입니다."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from alj_core.utils.windows_job import WindowsJobError
from judge.core.submission_status import command_status
from judge.utils.process import (
    DEFAULT_CHILD_STACK_LIMIT_BYTES,
    CommandResult,
    run_command_result,
    terminate_process_group,
)


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

    def test_windows_job_peak_and_memory_verdict_are_exposed(self) -> None:
        """Windows Job Object accounting is used instead of the unavailable Windows sampler."""

        class FakeWindowsJob:
            assigned_pid: int | None = None
            closed = False

            def assign(self, process) -> None:
                self.assigned_pid = process.pid

            @property
            def creation_flags(self) -> int:
                return 0

            def resume(self, process_id) -> None:
                self.resumed_pid = process_id

            def peak_memory_bytes(self) -> int:
                return 4096

            def memory_limit_exceeded(self, returncode, peak_memory_bytes) -> bool:
                self.asserted = (returncode, peak_memory_bytes)
                return True

            def terminate(self) -> None:
                raise AssertionError("normal completion must not terminate the job")

            def close(self) -> None:
                self.closed = True

        job = FakeWindowsJob()
        with patch("alj_core.utils.process.create_windows_job", return_value=job):
            result = run_command_result(
                [sys.executable, "-c", "raise SystemExit(3)"],
                timeout_ms=2000,
                memory_limit_bytes=4096,
            )

        self.assertIsNotNone(job.assigned_pid)
        self.assertEqual(job.resumed_pid, job.assigned_pid)
        self.assertEqual(job.asserted, (3, 4096))
        self.assertTrue(job.closed)
        self.assertEqual(result.memory_bytes, 4096)
        self.assertTrue(result.memory_limit_exceeded)
        self.assertEqual(command_status(result), ("memory_limit", "memory limit exceeded"))

    def test_windows_job_setup_failure_is_fail_closed(self) -> None:
        """A missing isolation boundary must stop the command before user code starts."""
        with tempfile.TemporaryDirectory(prefix="alj-windows-job-failure-") as tmp:
            marker = Path(tmp) / "started.txt"
            with patch(
                "alj_core.utils.process.create_windows_job",
                side_effect=WindowsJobError("job unavailable"),
            ):
                result = run_command_result(
                    [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"],
                    timeout_ms=2000,
                    memory_limit_bytes=4096,
                )

        self.assertFalse(marker.exists())
        self.assertEqual(result.returncode, 127)
        self.assertTrue(result.system_error)
        self.assertEqual(command_status(result)[0], "system_error")

    def test_windows_job_termination_also_kills_an_unassigned_parent(self) -> None:
        """Job termination must not strand a suspended process when assignment failed."""

        class FakeProcess:
            killed = False

            def poll(self):
                return None

            def kill(self) -> None:
                self.killed = True

        class FakeWindowsJob:
            terminated = False

            def terminate(self) -> None:
                self.terminated = True

        job = FakeWindowsJob()
        process = FakeProcess()
        terminate_process_group(process, job)
        self.assertTrue(job.terminated)
        self.assertTrue(process.killed)

    def test_windows_job_assignment_failure_reaps_suspended_parent(self) -> None:
        """AssignProcessToJobObject failure is fail-closed and cannot block in wait()."""

        class FakeProcess:
            pid = 123
            killed = False
            waited = False

            def poll(self):
                return 1 if self.killed else None

            def kill(self) -> None:
                self.killed = True

            def wait(self) -> int:
                self.waited = True
                return 1

        class FakeWindowsJob:
            creation_flags = 4
            terminated = False
            closed = False

            def assign(self, _process) -> None:
                raise WindowsJobError("assignment failed")

            def terminate(self) -> None:
                self.terminated = True

            def close(self) -> None:
                self.closed = True

        process = FakeProcess()
        job = FakeWindowsJob()
        with (
            patch("alj_core.utils.process.create_windows_job", return_value=job),
            patch("alj_core.utils.process.subprocess.Popen", return_value=process),
        ):
            result = run_command_result(["submission.exe"], timeout_ms=1000)

        self.assertTrue(job.terminated)
        self.assertTrue(job.closed)
        self.assertTrue(process.killed)
        self.assertTrue(process.waited)
        self.assertTrue(result.system_error)

    def test_time_limit_precedes_memory_limit_signal(self) -> None:
        result = CommandResult(
            124,
            b"",
            b"",
            100,
            4096,
            memory_limit_exceeded=True,
        )
        self.assertEqual(command_status(result), ("time_limit", "time limit exceeded"))

    def test_timeout_kills_child_process_tree(self) -> None:
        """타임아웃이 플랫폼별 격리 경계에 포함된 자식 프로세스까지 종료하는지 검증합니다."""
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

    @unittest.skipUnless(os.name == "nt", "Windows Job Object integration test")
    def test_windows_job_enforces_process_tree_memory_limit(self) -> None:
        """Windows의 job-wide committed-memory 상한이 실제 제출 프로세스에 적용되는지 검증합니다."""
        script = "chunks = [];\nwhile True: chunks.append(bytearray(1024 * 1024))"

        result = run_command_result(
            [sys.executable, "-c", script],
            timeout_ms=10_000,
            memory_limit_bytes=128 * 1024 * 1024,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.memory_limit_exceeded)
        self.assertEqual(command_status(result), ("memory_limit", "memory limit exceeded"))

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
