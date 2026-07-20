from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from commons.job_queue import BackgroundJobStore
from judge.core.compiler import prepare_user_submission
from judge.core.errors import JudgeError, SubmissionCompileError
from judge.web.app import create_app
from judge.web.source_history_metadata import write_source_history_metadata
from judge.web.source_history_paths import create_source_target
from judge.web.submission_store import SubmissionStore


class SubmissionStoreTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("javac"), "javac is required")
    def test_java_snapshot_preserves_public_class_filename(self):
        with tempfile.TemporaryDirectory(prefix="alj-submission-java-") as tmp:
            root = Path(tmp)
            source = root / "Main.java"
            source.write_text(
                "public class Main { public static void main(String[] args) {} }\n",
                encoding="utf-8",
            )
            store = SubmissionStore(root / "submissions", root / "legacy")
            item = store.create(
                source,
                problem_id="06",
                profile="full",
                language="java",
                source_mode="upload",
            )
            snapshot = store.source_path(item["submissionId"])
            run_dir = root / "runs" / "java-run"
            run_dir.mkdir(parents=True)

            prepared = prepare_user_submission(
                snapshot,
                run_dir,
                10000,
                root,
                language="java",
            )

            self.assertEqual(snapshot.name, "Main.java")
            self.assertEqual(prepared.language, "java")

    def test_terminal_lifecycle_is_not_overwritten_by_late_cancel(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-") as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("print(1)\n", encoding="utf-8")
            store = SubmissionStore(root / "submissions", root / "legacy")
            item = store.create(
                source,
                problem_id="06",
                profile="full",
                language="python",
                source_mode="text",
            )
            store.mark_running(item["submissionId"])
            store.complete(item["submissionId"], {"status": "accepted", "cases": []})
            store.cancel(item["submissionId"])

            detail = store.detail(item["submissionId"])
            self.assertEqual(detail["lifecycle"], "completed")
            self.assertEqual(detail["verdict"], "accepted")

    def test_terminal_callback_failure_does_not_starve_queue(self):
        store = BackgroundJobStore(max_running_jobs=1)
        second_finished = threading.Event()
        store.start(
            kind="first",
            title="first",
            problem_id="first",
            operation=lambda: {},
            terminal_callback=lambda _job: (_ for _ in ()).throw(RuntimeError("observer")),
        )
        store.start(
            kind="second",
            title="second",
            problem_id="second",
            operation=lambda: second_finished.set() or {},
        )
        self.assertTrue(second_finished.wait(2))

    def test_compile_failure_carries_typed_run_context(self):
        with tempfile.TemporaryDirectory(prefix="alj-submission-compile-") as tmp:
            root = Path(tmp)
            source = root / "main.cpp"
            source.write_text("int main( {\n", encoding="utf-8")
            run_dir = root / "cache" / "runs" / "compile-run"
            run_dir.mkdir(parents=True)

            with self.assertRaises(SubmissionCompileError) as raised:
                prepare_user_submission(source, run_dir, 5000, root, language="cpp")

            self.assertEqual(raised.exception.run_id, "compile-run")
            self.assertEqual(raised.exception.result["status"], "compile_error")
            self.assertEqual(raised.exception.result["runId"], "compile-run")
            self.assertIsInstance(raised.exception, JudgeError)

    def test_duplicate_source_creates_unique_persistent_records_and_survives_cache_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-") as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("print(1)\n", encoding="utf-8")
            legacy_root = root / "cache" / "web-submissions"
            store = SubmissionStore(root / "data" / "submissions", legacy_root)

            first = store.create(
                source,
                problem_id="06",
                profile="sample",
                language="python",
                source_mode="text",
            )
            second = store.create(
                source,
                problem_id="06",
                profile="sample",
                language="python",
                source_mode="text",
            )
            self.assertNotEqual(first["submissionId"], second["submissionId"])

            store.mark_running(first["submissionId"])
            store.complete(
                first["submissionId"],
                {
                    "runId": "run-1",
                    "problemId": "06",
                    "profile": "sample",
                    "language": "python",
                    "status": "accepted",
                    "cases": [{"case": "001", "status": "ok"}],
                    "metrics": {"maxTimeMs": 3, "maxMemoryBytes": 12},
                    "runDir": "/private/host/cache/runs/run-1",
                },
            )
            shutil_cache = root / "cache"
            shutil_cache.mkdir()
            shutil_cache.rmdir()

            restored = SubmissionStore(root / "data" / "submissions", legacy_root)
            detail = restored.detail(first["submissionId"])
            self.assertEqual(detail["sourceText"], "print(1)\n")
            self.assertEqual(detail["verdict"], "accepted")
            self.assertFalse(detail["artifactAvailable"])
            self.assertNotIn("runDir", detail["result"])
            self.assertEqual(restored.list()["total"], 2)

    def test_filters_pagination_order_failure_reconciliation_and_deletion(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-") as tmp:
            root = Path(tmp)
            source = root / "main.cpp"
            source.write_text("int main() {}\n", encoding="utf-8")
            legacy_root = root / "legacy"
            store = SubmissionStore(root / "submissions", legacy_root)
            ids = []
            for problem_id, profile in (("06", "sample"), ("07", "full"), ("08", "full")):
                item = store.create(
                    source,
                    problem_id=problem_id,
                    profile=profile,
                    language="cpp",
                    source_mode="upload",
                )
                ids.append(item["submissionId"])
            store.fail(ids[0], "compiler unavailable")
            store.complete(ids[1], {"status": "wrong_answer", "cases": []})
            store.bind_job(ids[1], "searchable-job")

            page = store.list(language="cpp", profile="full", order="oldest", page=1, page_size=1)
            self.assertEqual(page["total"], 2)
            self.assertEqual(page["pageSize"], 1)
            self.assertEqual(page["totalPages"], 2)
            self.assertEqual(
                store.list(status="system_error")["submissions"][0]["problemId"], "06"
            )
            self.assertEqual(store.list(query="main.cpp")["total"], 3)
            self.assertEqual(store.list(query="searchable-job")["total"], 1)

            restored = SubmissionStore(root / "submissions", legacy_root)
            self.assertEqual(restored.detail(ids[2])["lifecycle"], "interrupted")
            self.assertEqual(restored.delete(ids[1]), {"deleted": True, "submissionId": ids[1]})
            self.assertEqual(restored.list()["total"], 2)

    def test_legacy_last_run_is_exposed_without_modifying_original(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-legacy-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with patch.dict(os.environ, env, clear=True):
                source_id, source = create_source_target("06", "main.py", "python")
                source.write_text("print(1)\n", encoding="utf-8")
                metadata = write_source_history_metadata(source_id, source, "06", "text", "python")
                metadata["lastRun"] = {
                    "runId": "old-run",
                    "problemId": "06",
                    "profile": "sample",
                    "status": "accepted",
                    "savedAt": 1000,
                }
                (source.parent / "metadata.json").write_text(
                    json.dumps(metadata), encoding="utf-8"
                )
                original = (source.parent / "metadata.json").read_bytes()

                store = SubmissionStore()
                listed = store.list()
                legacy_id = f"legacy-{source_id}"
                self.assertEqual(listed["submissions"][0]["submissionId"], legacy_id)
                self.assertEqual(store.detail(legacy_id)["sourceText"], "print(1)\n")
                with self.assertRaisesRegex(Exception, "cannot be deleted"):
                    store.delete(legacy_id)
                self.assertEqual((source.parent / "metadata.json").read_bytes(), original)

    def test_delete_tombstone_prevents_legacy_ghost_record(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-legacy-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with patch.dict(os.environ, env, clear=True):
                source_id, source = create_source_target("06", "main.py", "python")
                source.write_text("print(1)\n", encoding="utf-8")
                metadata = write_source_history_metadata(source_id, source, "06", "text", "python")
                store = SubmissionStore()
                submission = store.create(
                    source,
                    problem_id="06",
                    profile="full",
                    language="python",
                    source_mode="text",
                )
                metadata["lastRun"] = {
                    "runId": "old-run",
                    "problemId": "06",
                    "status": "accepted",
                    "savedAt": 1000,
                }
                (source.parent / "metadata.json").write_text(
                    json.dumps(metadata), encoding="utf-8"
                )

                store.cancel(submission["submissionId"])
                store.delete(submission["submissionId"])
                self.assertEqual(store.list()["total"], 0)


class SubmissionApiTests(unittest.TestCase):
    def test_queued_job_executes_immutable_snapshot_and_active_delete_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-snapshot-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            blocker = threading.Event()
            executed_source = []

            def run_with_snapshot(problem_id, profile, source, *_args, **_kwargs):
                executed_source.append(source.read_text(encoding="utf-8"))
                return {
                    "runId": "snapshot-run",
                    "problemId": problem_id,
                    "profile": profile,
                    "status": "accepted",
                    "cases": [],
                }

            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "judge.web.services.run_problem_source_with_progress",
                    side_effect=run_with_snapshot,
                ),
            ):
                app = create_app()
                app.state.jobs.max_running_jobs = 1
                app.state.jobs.start(
                    kind="blocker",
                    title="blocker",
                    problem_id="blocker",
                    operation=lambda: blocker.wait(5) or {},
                )
                client = TestClient(app)
                response = client.post(
                    "/api/run/jobs",
                    data={
                        "problem_id": "06",
                        "profile": "full",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": "print('original')",
                        "language": "python",
                    },
                )
                submission_id = response.json()["target"]["submissionId"]
                active_delete = client.delete(f"/api/submissions/{submission_id}")
                active_clear = client.delete("/api/submissions?confirm=true")
                metadata = app.state.submissions.detail(submission_id)
                legacy_dir = (
                    Path(env["ALJ_CACHE_HOME"]) / "web-submissions" / metadata["legacySourceId"]
                )
                legacy_source = next(
                    path for path in legacy_dir.iterdir() if path.name != "metadata.json"
                )
                legacy_source.write_text("print('mutated')", encoding="utf-8")
                blocker.set()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and not executed_source:
                    time.sleep(0.01)
                while time.monotonic() < deadline:
                    lifecycle = app.state.submissions.detail(submission_id)["lifecycle"]
                    if lifecycle == "completed":
                        break
                    time.sleep(0.01)

            self.assertEqual(active_delete.status_code, 409, active_delete.text)
            self.assertEqual(active_clear.status_code, 409, active_clear.text)
            self.assertEqual(executed_source, ["print('original')"])
            self.assertEqual(lifecycle, "completed")

    def test_upload_stream_and_job_run_variants_link_submission_ids(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-variants-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }

            def result_for(problem_id, profile, *_args, **_kwargs):
                return {
                    "runId": f"run-{problem_id}",
                    "problemId": problem_id,
                    "profile": profile or "full",
                    "status": "accepted",
                    "cases": [],
                    "metrics": {},
                }

            def event_stream(problem_id, profile, *_args, **kwargs):
                kwargs["on_started"]()
                result = result_for(problem_id, profile)
                kwargs["on_result"](result)
                yield "event: result\ndata: {}\n\n"

            with (
                patch.dict(os.environ, env, clear=True),
                patch("judge.web.services.run_problem_source", side_effect=result_for),
                patch("judge.web.services.run_problem_events", side_effect=event_stream),
                patch(
                    "judge.web.services.run_problem_source_with_progress", side_effect=result_for
                ),
            ):
                app = create_app()
                client = TestClient(app)
                upload = client.post(
                    "/api/run/upload",
                    data={"problem_id": "06", "profile": "full", "language": "python"},
                    files={"file": ("main.py", b"print(1)\n", "text/x-python")},
                )
                stream = client.post(
                    "/api/run/stream",
                    data={
                        "problem_id": "07",
                        "profile": "sample",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": "print(2)",
                        "language": "python",
                    },
                )
                job = client.post(
                    "/api/run/jobs",
                    data={
                        "problem_id": "08",
                        "profile": "full",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": "print(3)",
                        "language": "python",
                    },
                )
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    job_state = client.get(f"/api/jobs/{job.json()['jobId']}").json()
                    if job_state["status"] in {"succeeded", "failed", "cancelled"}:
                        break
                    time.sleep(0.01)
                listed = client.get("/api/submissions", params={"status": "accepted"}).json()

            self.assertEqual(upload.status_code, 200, upload.text)
            self.assertTrue(upload.json()["submissionId"])
            self.assertTrue(stream.headers["x-submission-id"])
            self.assertTrue(job.json()["target"]["submissionId"])
            self.assertEqual(job_state["status"], "succeeded")
            self.assertEqual(listed["total"], 3)

    def test_cache_clear_preserves_submission_and_explicit_clear_requires_confirmation(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-cache-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with patch.dict(os.environ, env, clear=True):
                app = create_app()
                source = Path(tmp) / "main.py"
                source.write_text("print(1)\n", encoding="utf-8")
                submission = app.state.submissions.create(
                    source,
                    problem_id="06",
                    profile="full",
                    language="python",
                    source_mode="path",
                )
                run_dir = Path(env["ALJ_CACHE_HOME"]) / "runs" / "cache-run"
                run_dir.mkdir(parents=True)
                (run_dir / "result.json").write_text("{}\n", encoding="utf-8")
                app.state.submissions.complete(
                    submission["submissionId"],
                    {"runId": "cache-run", "status": "accepted", "cases": []},
                )
                client = TestClient(app)
                cleared_cache = client.post(
                    "/api/cache/clear",
                    json={"all_entries": True, "dry_run": False},
                )
                detail = client.get(f"/api/submissions/{submission['submissionId']}")
                unconfirmed = client.delete("/api/submissions")
                cleared_history = client.delete("/api/submissions?confirm=true")

            self.assertEqual(cleared_cache.status_code, 200, cleared_cache.text)
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(detail.json()["sourceText"], "print(1)\n")
            self.assertEqual(detail.json()["verdict"], "accepted")
            self.assertFalse(detail.json()["artifactAvailable"])
            self.assertEqual(unconfirmed.status_code, 400)
            self.assertEqual(cleared_history.json()["cleared"], 1)

    def test_typed_compile_error_is_recorded_without_path_leak(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-api-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            compile_error = SubmissionCompileError(
                "compile failed",
                run_id="compile-run",
                result={
                    "runId": "compile-run",
                    "status": "compile_error",
                    "compileLog": "/private/host/compile.log",
                },
            )
            with (
                patch.dict(os.environ, env, clear=True),
                patch("judge.web.services.run_problem_source", side_effect=compile_error),
            ):
                client = TestClient(create_app())
                response = client.post(
                    "/api/run",
                    json={
                        "problem_id": "06",
                        "profile": "full",
                        "source_mode": "text",
                        "filename": "main.cpp",
                        "source_text": "int main( {",
                        "language": "cpp",
                    },
                )
                submission = client.get(
                    "/api/submissions", params={"status": "compile_error"}
                ).json()["submissions"][0]
                detail = client.get(f"/api/submissions/{submission['submissionId']}").json()

            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(submission["verdict"], "compile_error")
            self.assertEqual(submission["runId"], "compile-run")
            self.assertNotIn("compileLog", detail["result"])

    def test_job_typed_compile_error_is_not_overwritten_by_terminal_callback(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-job-ce-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            compile_error = SubmissionCompileError(
                "compile failed",
                run_id="job-compile-run",
                result={"runId": "job-compile-run", "status": "compile_error"},
            )
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "judge.web.services.run_problem_source_with_progress",
                    side_effect=compile_error,
                ),
            ):
                app = create_app()
                client = TestClient(app)
                response = client.post(
                    "/api/run/jobs",
                    data={
                        "problem_id": "06",
                        "profile": "full",
                        "source_mode": "text",
                        "filename": "main.cpp",
                        "source_text": "int main( {",
                        "language": "cpp",
                    },
                )
                submission_id = response.json()["target"]["submissionId"]
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    job = client.get(f"/api/jobs/{response.json()['jobId']}").json()
                    if job["status"] in {"succeeded", "failed", "cancelled"}:
                        break
                    time.sleep(0.01)
                detail = client.get(f"/api/submissions/{submission_id}").json()

            self.assertEqual(job["status"], "failed")
            self.assertEqual(detail["lifecycle"], "completed")
            self.assertEqual(detail["verdict"], "compile_error")
            self.assertEqual(detail["runId"], "job-compile-run")

    def test_run_result_is_recorded_and_api_filters_validate(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-api-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            result = {
                "runId": "api-run",
                "problemId": "06",
                "profile": "sample",
                "language": "python",
                "status": "compile_error",
                "cases": [],
                "metrics": {},
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch("judge.web.services.run_problem_source", return_value=result),
            ):
                client = TestClient(create_app())
                response = client.post(
                    "/api/run",
                    json={
                        "problem_id": "06",
                        "profile": "sample",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": "not python",
                        "language": "python",
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                submission_id = response.json()["submissionId"]
                listed = client.get(
                    "/api/submissions",
                    params={"problem_id": "06", "status": "compile_error", "page_size": 1},
                )
                detail = client.get(f"/api/submissions/{submission_id}")
                invalid = client.get("/api/submissions", params={"status": "mystery"})
                deleted = client.delete(f"/api/submissions/{submission_id}")

            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual(listed.json()["total"], 1)
            self.assertEqual(detail.json()["verdict"], "compile_error")
            self.assertEqual(detail.json()["sourceText"], "not python")
            self.assertEqual(invalid.status_code, 422)
            self.assertEqual(deleted.json()["deleted"], True)

    def test_exception_and_queued_job_cancellation_are_terminal(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-api-") as tmp:
            env = {
                **os.environ,
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "judge.web.services.run_problem_source",
                    side_effect=RuntimeError("judge crashed"),
                ),
            ):
                client = TestClient(create_app())
                failed = client.post(
                    "/api/run",
                    json={
                        "problem_id": "06",
                        "profile": "full",
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": "print(1)",
                    },
                )
                self.assertEqual(failed.status_code, 500, failed.text)
                failure = client.get("/api/submissions", params={"status": "system_error"}).json()[
                    "submissions"
                ][0]
                self.assertEqual(failure["lifecycle"], "completed")
                self.assertEqual(failure["error"], "judge crashed")

                source = Path(tmp) / "queued.py"
                source.write_text("print(2)\n", encoding="utf-8")
                submission = client.app.state.submissions.create(
                    source,
                    problem_id="07",
                    profile="full",
                    language="python",
                    source_mode="path",
                )
                blocker = threading.Event()
                client.app.state.jobs.max_running_jobs = 1
                client.app.state.jobs.start(
                    kind="blocker",
                    title="blocker",
                    problem_id="blocker",
                    operation=lambda: blocker.wait(5) or {},
                )
                queued = client.app.state.jobs.start(
                    kind="judge-run",
                    title="queued",
                    problem_id="07",
                    operation=lambda: {},
                    target={"submissionId": submission["submissionId"]},
                    cancel_supported=True,
                )
                cancelled = client.post(f"/api/jobs/{queued.job_id}/cancel")
                blocker.set()

            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertEqual(cancelled.json()["status"], "cancelled")
            self.assertEqual(
                client.app.state.submissions.detail(submission["submissionId"])["lifecycle"],
                "cancelled",
            )

    def test_non_local_detail_and_delete_are_blocked(self):
        with tempfile.TemporaryDirectory(prefix="alj-submissions-api-") as tmp:
            source = Path(tmp) / "main.py"
            source.write_text("print(1)\n", encoding="utf-8")
            app = create_app(
                local_binding=False,
                remote_warning=True,
                submission_history_root=Path(tmp) / "submissions",
                legacy_source_history_root=Path(tmp) / "legacy",
            )
            submission = app.state.submissions.create(
                source,
                problem_id="06",
                profile="full",
                language="python",
                source_mode="path",
            )
            client = TestClient(app)
            detail = client.get(f"/api/submissions/{submission['submissionId']}")
            deleted = client.delete(f"/api/submissions/{submission['submissionId']}")

        self.assertEqual(detail.status_code, 403)
        self.assertEqual(deleted.status_code, 403)


if __name__ == "__main__":
    unittest.main()
