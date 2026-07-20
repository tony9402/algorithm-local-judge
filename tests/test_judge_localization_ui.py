from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JudgeLocalizationUiContractTest(unittest.TestCase):
    def test_primary_judge_information_architecture_is_korean(self) -> None:
        page = (ROOT / "judge/web/static/index.html").read_text(encoding="utf-8")

        for text in (
            "문제",
            "채점",
            "고급 옵션",
            "파일 이름",
            "소스 코드",
            "예제",
            "상태",
            "문제 팩",
            "캐시",
        ):
            self.assertIn(text, page)
        self.assertNotIn(">Problems<", page)
        self.assertNotIn(">Run<", page)
        self.assertNotIn(">Samples<", page)
        self.assertNotIn(">Status<", page)

    def test_legacy_cached_sources_are_collapsed_without_removing_controls(self) -> None:
        page = (ROOT / "judge/web/static/index.html").read_text(encoding="utf-8")

        self.assertIn('<details class="source-history">', page)
        self.assertNotIn('<details class="source-history" open>', page)
        self.assertIn("이전 캐시 코드(호환)", page)
        self.assertIn('id="sourceHistoryList"', page)

    def test_sample_internal_label_is_only_written_to_advanced_diagnostics(self) -> None:
        page = (ROOT / "judge/web/static/index.html").read_text(encoding="utf-8")
        samples = (ROOT / "judge/web/static/app/samples.js").read_text(encoding="utf-8")

        self.assertIn('id="sampleDiagnosticLabel"', page)
        self.assertIn('app.setText("sampleDiagnosticLabel", data.label', samples)
        sample_meta_call = samples.split('app.setText(\n    "sampleMeta",', 1)[1].split(");", 1)[0]
        self.assertNotIn("data.label", sample_meta_call)

    def test_signature_error_does_not_request_cosign_installation(self) -> None:
        packs = (ROOT / "judge/web/static/app/packs.js").read_text(encoding="utf-8")
        signature_branch = packs.split('lower.includes("sigstore")', 1)[1].split("}", 1)[0]

        self.assertNotIn("Cosign 설치", signature_branch)
        self.assertIn("앱을 업데이트", signature_branch)

    def test_dynamic_judge_labels_stay_korean(self) -> None:
        problems = (ROOT / "judge/web/static/app/problems.js").read_text(encoding="utf-8")
        state = (ROOT / "judge/web/static/app/state.js").read_text(encoding="utf-8")
        readiness = (ROOT / "judge/web/static/app/source-readiness.js").read_text(encoding="utf-8")
        run = (ROOT / "judge/web/static/app/run.js").read_text(encoding="utf-8")
        sources = (ROOT / "judge/web/static/app/sources.js").read_text(encoding="utf-8")
        submissions = (ROOT / "judge/web/static/app/submissions.js").read_text(encoding="utf-8")
        cases = (ROOT / "judge/web/static/app/cases.js").read_text(encoding="utf-8")
        page = (ROOT / "judge/web/static/index.html").read_text(encoding="utf-8")

        self.assertIn('"설치된 문제가 없습니다."', problems)
        self.assertNotIn('"No problems installed."', problems)
        self.assertIn('full: "전체"', state)
        self.assertIn('sample: "샘플"', state)
        self.assertIn('hidden: "숨김"', state)
        self.assertIn('"알 수 없는 언어"', readiness)
        self.assertIn('"코드 없음"', readiness)
        self.assertIn("알 수 없는 상태", sources)
        self.assertIn("이전 캐시 코드 기록은 유지됩니다.", submissions)
        self.assertIn('"케이스 정상"', cases)
        self.assertIn('"케이스 오류"', cases)
        self.assertNotIn("Cached Sources", submissions)
        self.assertNotIn('"Cases 정상"', cases)
        self.assertNotIn('"Cases 오류"', cases)
        self.assertIn('"줄 바꿈 해제"', run)
        self.assertIn("다운로드를 준비했습니다:", run)
        self.assertNotIn("(Copy)", page)
        self.assertNotIn("(Download)", page)
        self.assertNotIn("(Wrap)", page)
        self.assertNotIn("(Expand)", page)


if __name__ == "__main__":
    unittest.main()
