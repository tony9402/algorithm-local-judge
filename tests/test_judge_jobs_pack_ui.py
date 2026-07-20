from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JudgeJobsPackUiContractTest(unittest.TestCase):
    def test_job_center_has_responsive_semantics_and_named_progress(self) -> None:
        page = (ROOT / "judge/web/static/index.html").read_text(encoding="utf-8")
        jobs = (ROOT / "judge/web/static/app/jobs.js").read_text(encoding="utf-8")

        self.assertIn('aria-controls="jobsPanel"', page)
        self.assertIn('role="complementary"', page)
        self.assertIn('id="jobsAnnouncements"', page)
        self.assertIn('role="progressbar"', jobs)
        self.assertIn('aria-label="${app.escapeHtml(job.title', jobs)
        self.assertIn('panel.setAttribute("role", "dialog")', jobs)
        self.assertIn('panel.setAttribute("aria-modal", "true")', jobs)
        self.assertIn("announcedTerminalJobs", jobs)

    def test_queued_jobs_do_not_open_behind_pack_modal(self) -> None:
        jobs = (ROOT / "judge/web/static/app/jobs.js").read_text(encoding="utf-8")
        run_queued_body = jobs.split("async function runQueuedJob", 1)[1].split(
            "async function cancelJob", 1
        )[0]

        self.assertNotIn("openJobs(true)", run_queued_body)
        self.assertIn("onQueued(job)", run_queued_body)

    def test_pack_default_advanced_progress_and_fail_closed_contract(self) -> None:
        page = (ROOT / "judge/web/static/index.html").read_text(encoding="utf-8")
        packs = (ROOT / "judge/web/static/app/packs.js").read_text(encoding="utf-8")
        service = (ROOT / "judge/web/service_uploads.py").read_text(encoding="utf-8")

        self.assertIn('id="defaultPackInstallButton"', page)
        self.assertIn("<summary>고급 설치</summary>", page)
        self.assertIn('id="packProgress"', page)
        self.assertIn('id="packJobsButton"', page)
        self.assertIn("verifyOfficialInstall", packs)
        self.assertIn("checksumVerified !== true", packs)
        self.assertIn("signatureVerified !== true", packs)
        self.assertIn("require_pack=True", service)


if __name__ == "__main__":
    unittest.main()
