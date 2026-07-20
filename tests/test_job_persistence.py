"""로컬 작업 이력의 atomic 저장, 복원, 보존 정책을 검증합니다."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from commons.job_persistence import AtomicJsonFile, default_job_history_path
from commons.job_queue import (
    ACTIVE_STATUSES,
    JOB_HISTORY_SCHEMA_VERSION,
    TERMINAL_STATUSES,
    BackgroundJob,
    BackgroundJobStore,
)


class BackgroundJobPersistenceTest(unittest.TestCase):
    """재시작과 동시 완료 상황에서도 작업 이력 계약이 유지되는지 검증합니다."""

    def wait_for_terminal(
        self,
        store: BackgroundJobStore,
        job_id: str,
        timeout: float = 3.0,
    ) -> BackgroundJob:
        """백그라운드 작업이 terminal 상태가 될 때까지 짧게 기다립니다."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = store.get(job_id)
            if job is not None and job.status in TERMINAL_STATUSES:
                return job
            time.sleep(0.01)
        self.fail(f"job did not finish: {job_id}")

    def test_terminal_result_survives_store_restart(self) -> None:
        """완료 상태, 결과, 진행 로그는 새 store 인스턴스에서 복원돼야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-job-history-") as temporary:
            history_path = Path(temporary) / "jobs.json"
            store = BackgroundJobStore(persistence_path=history_path)
            job = store.start(
                kind="verify",
                title="Verify",
                problem_id="alpha",
                operation=lambda: {"passed": True, "runId": "persisted-run"},
                progress={"message": "queued"},
            )
            store.update_progress(job.job_id, "working", current=1, total=1)
            finished = self.wait_for_terminal(store, job.job_id)
            self.assertEqual(finished.status, "succeeded")

            restored = BackgroundJobStore(persistence_path=history_path)
            loaded = restored.get(job.job_id)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.status, "succeeded")
            self.assertEqual(loaded.result, {"passed": True, "runId": "persisted-run"})
            self.assertEqual(loaded.progress["current"], 1)
            self.assertEqual(loaded.last_log, "working")

    def test_active_jobs_restore_as_explicit_interrupted_failures(self) -> None:
        """대기·실행·취소 중 작업은 재실행하지 않고 interrupted 실패로 복원해야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-job-history-") as temporary:
            history_path = Path(temporary) / "jobs.json"
            jobs = [
                BackgroundJob(
                    job_id=f"active-{status}",
                    kind="pack",
                    title="Pack",
                    problem_id="alpha",
                    status=status,
                    progress={"message": f"{status} before restart"},
                )
                for status in sorted(ACTIVE_STATUSES)
            ]
            AtomicJsonFile(history_path).write(
                {
                    "schemaVersion": JOB_HISTORY_SCHEMA_VERSION,
                    "savedAt": datetime.now(UTC),
                    "jobs": [job.to_storage_dict() for job in jobs],
                }
            )

            restored = BackgroundJobStore(persistence_path=history_path)
            self.assertEqual(restored.running_count(), 0)
            self.assertEqual(restored.queued_count(), 0)
            for status in sorted(ACTIVE_STATUSES):
                with self.subTest(previous_status=status):
                    job = restored.get(f"active-{status}")
                    self.assertIsNotNone(job)
                    assert job is not None
                    self.assertEqual(job.status, "failed")
                    self.assertEqual(job.outcome, "failed")
                    self.assertEqual(job.error_kind, "interrupted")
                    self.assertIn("재시작", job.error or "")
                    self.assertEqual(job.failure_details[0]["previousStatus"], status)

            second_restart = BackgroundJobStore(persistence_path=history_path)
            self.assertTrue(all(job.status == "failed" for job in second_restart.list()))

    def test_dismiss_clear_ttl_and_max_jobs_persist(self) -> None:
        """삭제, 전체 정리, TTL stale 표시, 최대 보존 개수는 재시작 후에도 유지돼야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-job-history-") as temporary:
            history_path = Path(temporary) / "jobs.json"
            store = BackgroundJobStore(
                persistence_path=history_path,
                ttl_seconds=0,
                max_jobs=2,
                max_running_jobs=1,
            )
            job_ids = []
            for index in range(3):
                job = store.start(
                    kind="test",
                    title=f"Test {index}",
                    problem_id="alpha",
                    operation=lambda index=index: {"passed": True, "index": index},
                )
                job_ids.append(job.job_id)
                self.wait_for_terminal(store, job.job_id)

            restored = BackgroundJobStore(
                persistence_path=history_path,
                ttl_seconds=0,
                max_jobs=2,
            )
            self.assertIsNone(restored.get(job_ids[0]))
            retained = restored.list()
            self.assertEqual({job.job_id for job in retained}, set(job_ids[1:]))
            self.assertTrue(all(restored.job_dict(job)["status"] == "stale" for job in retained))

            self.assertTrue(restored.dismiss(job_ids[1]))
            self.assertEqual(
                restored.clear_completed(lambda job: job.problem_id == "alpha"),
                1,
            )
            self.assertEqual(
                BackgroundJobStore(persistence_path=history_path).list(),
                [],
            )

    def test_concurrent_completions_leave_valid_complete_snapshot(self) -> None:
        """동시 완료 뒤 JSON은 손상 없이 모든 terminal 작업을 포함해야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-job-history-") as temporary:
            history_path = Path(temporary) / "jobs.json"
            worker_count = 8
            barrier = threading.Barrier(worker_count + 1)
            store = BackgroundJobStore(
                persistence_path=history_path,
                max_jobs=worker_count,
                max_running_jobs=worker_count,
            )

            def operation(index: int) -> dict[str, object]:
                barrier.wait(timeout=3)
                return {"passed": True, "index": index}

            jobs = [
                store.start(
                    kind="concurrent",
                    title=f"Concurrent {index}",
                    problem_id="alpha",
                    operation=lambda index=index: operation(index),
                )
                for index in range(worker_count)
            ]
            barrier.wait(timeout=3)
            for job in jobs:
                self.wait_for_terminal(store, job.job_id)

            payload = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["jobs"]), worker_count)
            if os.name != "nt":
                self.assertEqual(history_path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(history_path.parent.stat().st_mode & 0o777, 0o700)
            restored = BackgroundJobStore(
                persistence_path=history_path,
                max_jobs=worker_count,
            )
            self.assertEqual(len(restored.list()), worker_count)
            self.assertTrue(all(job.status == "succeeded" for job in restored.list()))

    def test_corrupt_history_is_quarantined_and_store_recovers(self) -> None:
        """손상 JSON은 앱 시작을 막지 않고 격리되며 이후 정상 이력을 다시 기록해야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-job-history-") as temporary:
            root = Path(temporary)
            history_path = root / "jobs.json"
            history_path.write_text("{not-json", encoding="utf-8")

            store = BackgroundJobStore(persistence_path=history_path)
            self.assertEqual(store.list(), [])
            self.assertIn("unable to load", store.persistence_error or "")
            self.assertEqual(len(list(root.glob("jobs.json.corrupt-*"))), 1)

            job = store.start(
                kind="recovery",
                title="Recovery",
                problem_id="alpha",
                operation=lambda: {"passed": True},
            )
            self.wait_for_terminal(store, job.job_id)
            self.assertIsNone(store.persistence_error)
            self.assertEqual(
                BackgroundJobStore(persistence_path=history_path).get(job.job_id).status,
                "succeeded",
            )

    def test_default_app_paths_are_separate_and_under_data_home(self) -> None:
        """Judge와 Problem Studio는 같은 데이터 홈 아래 서로 다른 파일을 사용해야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-job-history-") as temporary:
            with patch.dict(os.environ, {"ALJ_DATA_HOME": temporary}):
                judge_path = default_job_history_path("judge")
                studio_path = default_job_history_path("problem-studio")
            data_home = Path(temporary).resolve()
            self.assertEqual(judge_path.parent, data_home / "jobs")
            self.assertEqual(studio_path.parent, data_home / "jobs")
            self.assertNotEqual(judge_path, studio_path)


if __name__ == "__main__":
    unittest.main()
