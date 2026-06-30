"""제출 실행 경로 생성의 병렬 안전성을 검증합니다."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from alj_core.submission_paths import new_run_dir


class SubmissionPathTest(unittest.TestCase):
    """제출 실행 디렉터리 생성 테스트를 묶습니다."""

    def test_new_run_dir_is_atomic_under_parallel_creation(self) -> None:
        """동시에 같은 초의 run id를 잡아도 모든 호출은 고유한 디렉터리를 받아야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-run-dir-race-") as tmp:
            root = Path(tmp)

            class FixedDatetime:
                @classmethod
                def now(cls):
                    return cls()

                def strftime(self, _format: str) -> str:
                    return "20260101-000000"

            results: list[Path] = []
            errors: list[BaseException] = []
            result_lock = threading.Lock()
            thread_count = 24
            start_barrier = threading.Barrier(thread_count)

            def create_run_dir() -> None:
                try:
                    start_barrier.wait(timeout=3)
                    _run_id, run_dir = new_run_dir(root)
                    with result_lock:
                        results.append(run_dir)
                except BaseException as exc:  # noqa: BLE001 - the test asserts no thread fails.
                    with result_lock:
                        errors.append(exc)

            with patch("alj_core.submission_paths.datetime", FixedDatetime):
                threads = [threading.Thread(target=create_run_dir) for _ in range(thread_count)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=3)

            self.assertEqual(errors, [])
            self.assertEqual(len(results), thread_count)
            self.assertEqual(len({path.name for path in results}), thread_count)
            self.assertTrue(all(path.exists() for path in results))


if __name__ == "__main__":
    unittest.main()
