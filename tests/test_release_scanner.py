"""릴리스 산출물 스캐너가 공지 파일, 정적 자산, 체크섬, 플랫폼 대상을 올바르게 검증하는지 확인하는 모듈입니다."""

from __future__ import annotations

import hashlib
import tarfile
import tempfile
import unittest
from pathlib import Path

from judge.core.checksums import write_sha256_sidecar
from judge.core.errors import JudgeError
from scripts.scan_release_artifact import (
    scan_artifact,
    scan_standalone_archive,
    validate_platform_targets,
)
from tests.e2e.pack_fixtures import create_minimal_pack


class ReleaseScannerTest(unittest.TestCase):
    """릴리스 스캐너 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def make_standalone_archive(
        self,
        root: Path,
        *,
        include_notice: bool = True,
        include_static: bool = True,
        include_studio_launcher: bool = True,
        include_studio_static: bool = True,
    ) -> Path:
        """독립 실행 아카이브 테스트가 후속 API 호출이나 명령 실행에 사용할 임시 리소스를 준비합니다.

        Args:
            root (Path): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.
            include_notice (bool): 독립 실행 산출물에 제3자 고지 파일을 넣을지 결정하는 플래그입니다.
            include_static (bool): 독립 실행 산출물에 정적 웹 자산을 넣을지 결정하는 플래그입니다.
            include_studio_launcher (bool): Problem Studio 실행기를 포함할지 결정합니다.
            include_studio_static (bool): Problem Studio 정적 자산을 포함할지 결정합니다.

        Returns:
            Path: 스캐너 검증에 사용할 독립 실행 패키지 아카이브 경로입니다.
        """
        app = root / "algorithm-local-judge"
        (app / "bin").mkdir(parents=True)
        (app / "bin" / "judge").write_text("#!/bin/sh\n", encoding="utf-8")
        if include_studio_launcher:
            (app / "bin" / "problem-studio").write_text("#!/bin/sh\n", encoding="utf-8")
        (app / "README.md").write_text("readme\n", encoding="utf-8")
        if include_notice:
            (app / "THIRD_PARTY_NOTICES.md").write_text("notices\n", encoding="utf-8")
        if include_static:
            static = app / "bin" / "web" / "static"
            (static / "app").mkdir(parents=True)
            (static / "styles").mkdir(parents=True)
            (static / "app.js").write_text("import './app/main.js';\n", encoding="utf-8")
            (static / "styles.css").write_text("@import './styles/base.css';\n", encoding="utf-8")
            (static / "index.html").write_text("<div></div>\n", encoding="utf-8")
            (static / "app" / "main.js").write_text("export {};\n", encoding="utf-8")
            (static / "styles" / "base.css").write_text("body {}\n", encoding="utf-8")
        if include_studio_static:
            studio_static = app / "bin" / "studio-web" / "static"
            (studio_static / "app").mkdir(parents=True)
            (studio_static / "styles").mkdir(parents=True)
            (studio_static / "fragments").mkdir(parents=True)
            (studio_static / "vendor" / "codemirror").mkdir(parents=True)
            (studio_static / "app.js").write_text("import './app/main.js';\n", encoding="utf-8")
            (studio_static / "styles.css").write_text(
                "@import './styles/base.css';\n",
                encoding="utf-8",
            )
            (studio_static / "index.html").write_text("<div></div>\n", encoding="utf-8")
            (studio_static / "app" / "main.js").write_text("export {};\n", encoding="utf-8")
            (studio_static / "styles" / "base.css").write_text("body {}\n", encoding="utf-8")
            (studio_static / "fragments" / "workspace.html").write_text(
                "<main></main>\n",
                encoding="utf-8",
            )
            (studio_static / "vendor" / "codemirror" / "codemirror.min.css").write_text(
                ".CodeMirror {}\n",
                encoding="utf-8",
            )
            (studio_static / "vendor" / "codemirror" / "codemirror.min.js").write_text(
                "window.CodeMirror = {};\n",
                encoding="utf-8",
            )

        checksum_lines = []
        for path in sorted(item for item in app.rglob("*") if item.is_file()):
            if path.name == "checksums.txt":
                continue
            checksum_lines.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                f"{path.relative_to(app).as_posix()}"
            )
        (app / "checksums.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

        archive_path = root / "algorithm-local-judge-0.1.0-macos-arm64.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(app, arcname=app.name)
        return archive_path

    def test_standalone_requires_third_party_notice_and_static_assets(self) -> None:
        """독립 실행 요구 제3자 제3자 고지 및 정적 자산 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-release-scan-") as tmp:
            root = Path(tmp)
            missing_notice = self.make_standalone_archive(root / "notice", include_notice=False)
            missing_static = self.make_standalone_archive(root / "static", include_static=False)

            with self.assertRaisesRegex(JudgeError, "THIRD_PARTY_NOTICES"):
                scan_standalone_archive(missing_notice)
            with self.assertRaisesRegex(JudgeError, "static"):
                scan_standalone_archive(missing_static)

    def test_standalone_accepts_required_notice_static_and_checksums(self) -> None:
        """독립 실행 허용 필수 고지 정적 및 체크섬 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-release-scan-") as tmp:
            archive_path = self.make_standalone_archive(Path(tmp))

            scan_standalone_archive(archive_path)

    def test_standalone_requires_problem_studio_launcher_and_vendor_assets(self) -> None:
        """통합 산출물에서 Studio 실행기와 vendor 자산 누락을 각각 거부합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-release-scan-") as tmp:
            root = Path(tmp)
            missing_launcher = self.make_standalone_archive(
                root / "launcher",
                include_studio_launcher=False,
            )
            missing_static = self.make_standalone_archive(
                root / "studio-static",
                include_studio_static=False,
            )

            with self.assertRaisesRegex(JudgeError, "bin/problem-studio executable"):
                scan_standalone_archive(missing_launcher)
            with self.assertRaisesRegex(JudgeError, "studio-web/static"):
                scan_standalone_archive(missing_static)

    def test_pack_scan_requires_sidecar_checksum(self) -> None:
        """패키지 스캔 요구 동반 파일 체크섬 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-release-pack-scan-") as tmp:
            pack_path = create_minimal_pack(Path(tmp) / "basic-1-macos-arm64.aljpack")

            with self.assertRaisesRegex(JudgeError, "missing checksum sidecar"):
                scan_artifact(pack_path)

            write_sha256_sidecar(pack_path)
            scan_artifact(pack_path)

    def test_platform_targets_only_fail_when_requested(self) -> None:
        """플랫폼 대상 요청된 경우만 실패 요청된 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        artifacts = [Path("dist/packs/basic-1-macos-arm64.aljpack")]

        validate_platform_targets(artifacts, ["macos-arm64"])
        with self.assertRaisesRegex(JudgeError, "linux-amd64"):
            validate_platform_targets(artifacts, ["linux-amd64"])


if __name__ == "__main__":
    unittest.main()
