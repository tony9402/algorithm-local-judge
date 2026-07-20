"""Problem Studio S6 작성 효율 UI와 기준 정답 전환 계약을 검증합니다."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from problem_studio.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]


class ProblemStudioS6UiTest(unittest.TestCase):
    """실패 deep link, bulk 필터, 단일 작업 toast와 안전 삭제 계약을 고정합니다."""

    def test_s6_frontend_contracts_are_present(self) -> None:
        """S6 control과 상태 연결이 정적 asset에 포함되어야 합니다."""
        fragment = (ROOT / "problem_studio/web/static/fragments/workspace-modals.html").read_text()
        bulk = (ROOT / "problem_studio/web/static/app/actions/build-bulk.js").read_text()
        jobs = (ROOT / "problem_studio/web/static/app/jobs-view.js").read_text()
        feedback = (ROOT / "problem_studio/web/static/app/feedback.js").read_text()
        app = (ROOT / "problem_studio/web/static/app.js").read_text()

        for control_id in (
            "bulkProblemSearchInput",
            "bulkProblemFolderFilter",
            "bulkProblemStatusFilter",
            "bulkDeselectAllButton",
        ):
            self.assertIn(control_id, fragment)
        self.assertIn("bulk-selection-sticky", fragment)
        self.assertIn("currentProblemResult", bulk)
        self.assertIn("bulkSelectedProblemIds", bulk)
        for action in ("file", "solution", "artifact"):
            self.assertIn(f'data-job-failure-action="{action}"', jobs)
        self.assertIn("showOperationAlert", jobs)
        self.assertIn("data-operation-id", feedback)
        self.assertIn("async function openFailureTarget", app)

    def test_reference_delete_uses_the_confirmed_accepted_replacement(self) -> None:
        """클라이언트가 고른 다른 AC 파일만 새 기준 정답으로 지정할 수 있습니다."""
        directory = tempfile.TemporaryDirectory(prefix="alj-studio-s6-")
        self.addCleanup(directory.cleanup)
        workspace = Path(directory.name)
        client = TestClient(create_app(workspace))

        created = client.post(
            "/api/problems",
            json={"problem_id": "alpha", "title": "Alpha"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        for name in ("a_reference", "z_reference"):
            response = client.post(
                "/api/problems/alpha/solutions/create",
                json={"name": name, "expected": "ac", "language": "cpp"},
            )
            self.assertEqual(response.status_code, 200, response.text)

        deleted = client.request(
            "DELETE",
            "/api/problems/alpha/solutions",
            json={
                "path": "solutions/main_solution.ac.cpp",
                "replacement": "solutions/z_reference.ac.cpp",
            },
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertTrue(deleted.json()["referenceChanged"])
        self.assertEqual(deleted.json()["replacement"], "solutions/z_reference.ac.cpp")
        self.assertEqual(
            deleted.json()["metadata"]["tools"]["solution"],
            "solutions/z_reference.ac.cpp",
        )

    def test_ui_regression_contracts_keep_drawers_narrow_and_pack_gate_visible(self) -> None:
        """모바일 서랍·모달 focus·팩 선행조건의 정적 계약을 유지합니다."""
        static_root = ROOT / "problem_studio/web/static"
        modal = (static_root / "app/modal.js").read_text()
        build_status = (static_root / "app/actions/build-status.js").read_text()
        workspace = (static_root / "fragments/workspace.html").read_text()
        dialogs = (static_root / "styles/dialogs.css").read_text()
        jobs = (static_root / "styles/jobs.css").read_text()
        resources = (static_root / "app/resources-view.js").read_text()
        self.assertIn("activeModalTriggerAction", modal)
        self.assertIn("modalTriggerFallback", modal)
        self.assertIn("packPrerequisiteMissing", build_status)
        self.assertIn('aria-label="문제 제작 단계"', workspace)
        self.assertIn('aria-label="업로드할 솔루션 파일 선택"', workspace)
        self.assertIn("width: min(520px, 100%);", dialogs)
        self.assertIn("width: min(520px, 100%);", jobs)
        self.assertIn("resource-empty-state", resources)

    def test_reference_delete_rejects_non_accepted_replacement(self) -> None:
        """WA 파일은 존재하더라도 기준 정답 대체 대상으로 승인하지 않습니다."""
        directory = tempfile.TemporaryDirectory(prefix="alj-studio-s6-invalid-")
        self.addCleanup(directory.cleanup)
        workspace = Path(directory.name)
        client = TestClient(create_app(workspace))
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Alpha"})
        created = client.post(
            "/api/problems/alpha/solutions/create",
            json={"name": "wrong", "expected": "wa", "language": "cpp"},
        )
        self.assertEqual(created.status_code, 200, created.text)

        deleted = client.request(
            "DELETE",
            "/api/problems/alpha/solutions",
            json={
                "path": "solutions/main_solution.ac.cpp",
                "replacement": "solutions/wrong.wa.cpp",
            },
        )
        self.assertEqual(deleted.status_code, 400, deleted.text)
        self.assertIn("accepted solution", deleted.json()["detail"])
        self.assertTrue((workspace / "problems/alpha/solutions/main_solution.ac.cpp").exists())


if __name__ == "__main__":
    unittest.main()
