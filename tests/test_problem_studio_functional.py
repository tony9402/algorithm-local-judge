from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from judge.core.errors import JudgeError
from problem_studio.core.bulk import build_all_problem_packs
from problem_studio.web.app import create_app


class ProblemStudioFunctionalTest(unittest.TestCase):
    """Functional safety net for problem-studio refactoring."""

    def make_client(self) -> tuple[tempfile.TemporaryDirectory[str], TestClient, Path]:
        directory = tempfile.TemporaryDirectory(prefix="alj-problem-studio-functional-")
        workspace = Path(directory.name)
        return directory, TestClient(create_app(workspace)), workspace

    def sse_events(self, text: str) -> list[tuple[str, dict]]:
        events = []
        for block in text.strip().split("\n\n"):
            if not block:
                continue
            event = "message"
            data_lines = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                if line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
            events.append((event, json.loads("\n".join(data_lines))))
        return events

    def poll_job(self, client: TestClient, problem_id: str, job_id: str) -> dict:
        status = {}
        for _ in range(50):
            response = client.get(f"/api/problems/{problem_id}/packs/jobs/{job_id}")
            self.assertEqual(response.status_code, 200, response.text)
            status = response.json()
            if status["status"] != "running":
                return status
            time.sleep(0.01)
        self.fail("background job did not finish")

    def test_problem_authoring_metadata_and_file_safety_contract(self) -> None:
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)

        created = client.post(
            "/api/problems",
            json={"problem_id": "alpha", "title": "Original", "folder": "Basics"},
        )
        self.assertEqual(created.status_code, 200, created.text)

        patched = client.patch(
            "/api/problems/alpha/metadata",
            json={
                "metadata": {
                    "title": "Updated",
                    "folder": "Graphs",
                    "defaultProfile": "sample",
                    "limits": {"userTimeoutMs": 1234},
                }
            },
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["problemId"], "alpha")
        self.assertEqual(patched.json()["title"], "Updated")

        detail = client.get("/api/problems/alpha")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["metadata"]["folder"], "Graphs")
        self.assertEqual(detail.json()["metadata"]["defaultProfile"], "sample")

        metadata_file = json.loads(
            (workspace / "problems" / "alpha" / "problem.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata_file["title"], "Updated")
        self.assertEqual(metadata_file["limits"]["userTimeoutMs"], 1234)

        rejected = client.get("/api/problems/alpha/files/%2E%2E/escaped.txt")
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertIn("invalid problem file path", rejected.json()["detail"])

    def test_problem_id_can_be_renamed_without_losing_files(self) -> None:
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post(
            "/api/problems",
            json={"problem_id": "alpha", "title": "Renamable", "folder": "Basics"},
        )
        client.put(
            "/api/problems/alpha/files/notes.md",
            json={"content": "keep me\n"},
        )

        renamed = client.patch("/api/problems/alpha/id", json={"problem_id": "beta"})

        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["previousProblemId"], "alpha")
        self.assertEqual(renamed.json()["problemId"], "beta")
        self.assertFalse((workspace / "problems" / "alpha").exists())
        self.assertTrue((workspace / "problems" / "beta" / "notes.md").exists())
        metadata = json.loads(
            (workspace / "problems" / "beta" / "problem.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["problemId"], "beta")
        self.assertEqual(metadata["title"], "Renamable")
        self.assertEqual(renamed.json()["workspace"]["problemIds"], ["beta"])

        old_detail = client.get("/api/problems/alpha")
        self.assertEqual(old_detail.status_code, 400, old_detail.text)
        new_note = client.get("/api/problems/beta/files/notes.md")
        self.assertEqual(new_note.status_code, 200, new_note.text)
        self.assertEqual(new_note.json()["content"], "keep me\n")

    def test_problem_id_rename_rejects_conflicts_and_unsafe_ids(self) -> None:
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Alpha"})
        client.post("/api/problems", json={"problem_id": "beta", "title": "Beta"})

        duplicate = client.patch("/api/problems/alpha/id", json={"problem_id": "beta"})
        self.assertEqual(duplicate.status_code, 400, duplicate.text)
        self.assertIn("problem already exists", duplicate.json()["detail"])

        unsafe = client.patch("/api/problems/alpha/id", json={"problem_id": "../escaped"})
        self.assertEqual(unsafe.status_code, 400, unsafe.text)
        self.assertIn("invalid problem id", unsafe.json()["detail"])

    def test_generate_stream_reports_compile_error_event(self) -> None:
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Broken Cases"})
        client.put(
            "/api/problems/alpha/files/generator/cases.yml",
            json={"content": "profiles:\n  hidden:\n    cases: not-a-list\n"},
        )

        response = client.post(
            "/api/problems/alpha/generate/stream",
            json={"profile": "hidden", "force": True},
        )

        self.assertEqual(response.status_code, 200, response.text)
        events = self.sse_events(response.text)
        self.assertEqual(events[-1][0], "error")
        self.assertIn("cases.yml compile failed", events[-1][1]["message"])
        self.assertFalse(any(event == "result" for event, _ in events))

    def test_tools_and_solution_validation_contracts(self) -> None:
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Tools"})
        compiled_path = workspace / ".judge-cache" / "tools" / "generator"

        with patch(
            "problem_studio.web.routes.tools.compile_problem_tool",
            return_value=compiled_path,
        ) as mocked_compile:
            response = client.post(
                "/api/problems/alpha/tools/compile",
                json={"tool": "generator"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["tools"]["generator"], str(compiled_path))
        self.assertEqual(mocked_compile.call_args.args[:2], ("alpha", "generator"))

        invalid_upload = client.post(
            "/api/problems/alpha/solutions/upload",
            files=[("files", ("notes.txt", b"not source\n", "text/plain"))],
        )
        self.assertEqual(invalid_upload.status_code, 400, invalid_upload.text)
        self.assertIn("unsupported solution extension", invalid_upload.json()["detail"])

        invalid_create = client.post(
            "/api/problems/alpha/solutions/create",
            json={"name": "bad token", "expected": "oops", "language": "cpp"},
        )
        self.assertEqual(invalid_create.status_code, 400, invalid_create.text)
        self.assertIn("unknown expected result token", invalid_create.json()["detail"])

    def test_background_pack_job_failure_and_download_safety(self) -> None:
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Pack"})

        with patch(
            "problem_studio.web.routes.packs.build_problem_pack",
            side_effect=JudgeError("pack failed"),
        ):
            started = client.post(
                "/api/problems/alpha/packs/build",
                json={"pack_id": "basic", "verify_profile": "hidden"},
            )
        self.assertEqual(started.status_code, 200, started.text)
        failed = self.poll_job(client, "alpha", started.json()["jobId"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"], "pack failed")

        outside = workspace.parent / "outside.aljpack"
        outside.write_bytes(b"outside")
        self.addCleanup(lambda: outside.exists() and outside.unlink())
        fake_result = {
            "archivePath": str(outside),
            "archiveLabel": "outside.aljpack",
            "packId": "basic",
            "platformId": "test",
            "problems": ["alpha"],
            "solutionChecks": [],
        }
        with patch(
            "problem_studio.web.routes.packs.build_problem_pack",
            return_value=fake_result,
        ):
            started = client.post(
                "/api/problems/alpha/packs/build",
                json={"pack_id": "basic", "verify_profile": "hidden"},
            )
        succeeded = self.poll_job(client, "alpha", started.json()["jobId"])
        self.assertEqual(succeeded["status"], "succeeded")

        download = client.get(
            f"/api/problems/alpha/packs/jobs/{started.json()['jobId']}/download"
        )
        self.assertEqual(download.status_code, 400, download.text)
        self.assertIn("outside the output directory", download.json()["detail"])

    def test_bulk_build_rejects_unknown_ids_and_skips_pack_on_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-functional-") as tmp:
            workspace = Path(tmp)
            with patch("problem_studio.core.bulk.discover_problem_ids", return_value=["01"]):
                with self.assertRaisesRegex(JudgeError, "unknown problem id"):
                    build_all_problem_packs(
                        workspace,
                        "basic",
                        Path("dist/packs"),
                        problem_ids=["01", "02"],
                    )

            def failed_full_test(*args, **kwargs) -> dict:
                return {
                    "problemId": args[1],
                    "passed": False,
                    "summary": "expected mismatch",
                    "solutionVerification": {"checks": [{"passed": False}]},
                }

            with (
                patch("problem_studio.core.bulk.discover_problem_ids", return_value=["01"]),
                patch(
                    "problem_studio.core.bulk.run_problem_full_test",
                    side_effect=failed_full_test,
                ),
                patch("problem_studio.core.bulk.build_problem_pack_bundle") as mocked_pack,
            ):
                result = build_all_problem_packs(
                    workspace,
                    "basic",
                    Path("dist/packs"),
                    problem_ids=["01"],
                )

        self.assertFalse(result["passed"])
        self.assertEqual(result["packCount"], 0)
        self.assertEqual(result["failedCount"], 1)
        mocked_pack.assert_not_called()

    def test_bulk_build_deduplicates_ids_and_forwards_solution_checks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-functional-") as tmp:
            workspace = Path(tmp)

            def passed_full_test(*args, **kwargs) -> dict:
                problem_id = args[1]
                return {
                    "problemId": problem_id,
                    "passed": True,
                    "summary": "ok",
                    "solutionVerification": {
                        "checks": [{"problemId": problem_id, "passed": True}]
                    },
                }

            with (
                patch("problem_studio.core.bulk.discover_problem_ids", return_value=["01", "02"]),
                patch(
                    "problem_studio.core.bulk.run_problem_full_test",
                    side_effect=passed_full_test,
                ),
                patch(
                    "problem_studio.core.bulk.build_problem_pack_bundle",
                    return_value={
                        "archiveLabel": "dist/packs/basic.aljpack",
                        "problems": ["01", "02"],
                    },
                ) as mocked_pack,
            ):
                result = build_all_problem_packs(
                    workspace,
                    "basic",
                    Path("dist/packs"),
                    problem_ids=["01", "01", "02"],
                )

        self.assertTrue(result["passed"])
        self.assertEqual(result["problemCount"], 2)
        self.assertEqual([item["problemId"] for item in result["problems"]], ["01", "02"])
        self.assertEqual(mocked_pack.call_args.args[1], ["01", "02"])
        self.assertEqual(
            mocked_pack.call_args.kwargs["solution_checks"],
            [{"problemId": "01", "passed": True}, {"problemId": "02", "passed": True}],
        )


if __name__ == "__main__":
    unittest.main()
