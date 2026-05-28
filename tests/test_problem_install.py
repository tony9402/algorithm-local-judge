"""문제 설치 기능의 GitHub 입력 해석, 신뢰 정책, 체크섬, 다운로드 제한을 검증하는 테스트 모듈입니다."""

from __future__ import annotations

import hashlib
import io
import os
import ssl
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from judge.core.errors import JudgeError, LimitExceededError
from judge.core.problem import discover_problem_ids
from judge.core.remote import (
    download_asset,
    download_problem_pack_from_github,
    download_problem_pack_from_url,
    github_repository_from_source,
    install_problem_source_archive,
    install_problem_source_package,
    official_pack_repository,
    select_pack_asset,
)
from judge.core.remote_archive import safe_extract_zip
from judge.core.remote_trust import (
    add_user_trusted_repository,
    is_trusted_repository,
    remove_user_trusted_repository,
)
from judge.utils.hashing import sha256_file
from tests.e2e.pack_fixtures import create_minimal_pack


class ProblemInstallTest(unittest.TestCase):
    """문제 설치 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_github_repository_from_source_accepts_common_forms(self) -> None:
        """GitHub 저장소 소스 허용 공통 형식 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        self.assertEqual(
            github_repository_from_source("tony9402/algorithm-package"),
            "tony9402/algorithm-package",
        )
        self.assertEqual(
            github_repository_from_source("https://github.com/tony9402/algorithm-package"),
            "tony9402/algorithm-package",
        )
        self.assertEqual(
            github_repository_from_source("git@github.com:tony9402/algorithm-package.git"),
            "tony9402/algorithm-package",
        )

    def test_official_repository_defaults_to_algorithm_package(self) -> None:
        """공식 저장소 기본값 알고리즘 패키지 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(official_pack_repository(), "tony9402/algorithm-package")

    def test_github_repository_from_source_rejects_non_github_source(self) -> None:
        """GitHub 저장소 소스 거부 비 GitHub 소스 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        self.assertIsNone(github_repository_from_source("not a repository"))
        self.assertIsNone(github_repository_from_source("https://example.com/owner/repo"))

    def test_select_pack_asset_prefers_requested_asset(self) -> None:
        """선택 패키지 자산 우선 선택 요청된 자산 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        assets = [
            {"name": "notes.txt", "browser_download_url": "https://example.com/notes.txt"},
            {
                "name": "basic-1-macos-arm64.aljpack",
                "browser_download_url": "https://example.com/basic.aljpack",
            },
        ]

        selected = select_pack_asset(assets, "basic-1-macos-arm64.aljpack")

        self.assertEqual(selected["name"], "basic-1-macos-arm64.aljpack")

    def test_select_pack_asset_requires_pack_assets(self) -> None:
        """선택 패키지 자산 요구 패키지 자산 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with self.assertRaises(JudgeError):
            select_pack_asset([{"name": "notes.txt"}], None)

    def test_trusted_repository_policy_uses_default_owner_and_user_allowlist(self) -> None:
        """신뢰된 저장소 정책 사용 기본 소유자 및 사용자 허용 목록 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-trusted-repo-test-") as tmp:
            with patch.dict(os.environ, {"ALJ_DATA_HOME": str(Path(tmp) / "data")}, clear=True):
                self.assertTrue(is_trusted_repository("tony9402/algorithm-package"))
                self.assertFalse(is_trusted_repository("https://github.com/tony9402/other"))
                self.assertFalse(is_trusted_repository("other/problems"))

                self.assertEqual(add_user_trusted_repository("other/problems"), "other/problems")
                self.assertTrue(is_trusted_repository("other/problems"))

                self.assertEqual(
                    remove_user_trusted_repository("other/problems"),
                    "other/problems",
                )
                self.assertFalse(is_trusted_repository("other/problems"))

    def test_install_source_package_exposes_problems(self) -> None:
        """설치 소스 패키지 노출 문제 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-source-install-test-") as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            problem = package / "problems" / "alpha"
            problem.mkdir(parents=True)
            (package / "testlib.h").write_text("// testlib\n", encoding="utf-8")
            (problem / "problem.json").write_text(
                '{"problemId":"alpha","title":"Alpha"}',
                encoding="utf-8",
            )
            env = {**os.environ, "ALJ_DATA_HOME": str(tmp_path / "data")}

            with patch.dict(os.environ, env, clear=True):
                result = install_problem_source_package(
                    package,
                    repository="tony9402/algorithm-package",
                    ref="main",
                    commit_sha="abc123",
                )

                self.assertEqual(result["installType"], "source")
                self.assertEqual(result["problemCount"], 1)
                self.assertIn("problem tools run locally", result["trustWarning"])
                self.assertIn("alpha", discover_problem_ids())
                installed = Path(result["installedPath"])
                self.assertTrue((installed / "source.json").exists())
                self.assertTrue((installed / "problems" / "testlib.h").exists())

    def test_source_archive_rejects_unsafe_member_paths(self) -> None:
        """소스 아카이브 거부 안전하지 않은 멤버 경로 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-source-archive-test-") as tmp:
            archive = Path(tmp) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../escaped.txt", "bad")

            with self.assertRaises(JudgeError):
                install_problem_source_archive(archive, repository="owner/repo", ref="main")

    def test_source_archive_rejects_symlink_member(self) -> None:
        """소스 아카이브 거부 심볼릭 링크 멤버 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-source-archive-link-test-") as tmp:
            archive = Path(tmp) / "unsafe-link.zip"
            link = zipfile.ZipInfo("package/problems/alpha/problem.json")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr(link, "target")

            with self.assertRaises(JudgeError) as raised:
                install_problem_source_archive(archive, repository="owner/repo", ref="main")

            self.assertIn("unsafe link in source archive", str(raised.exception))

    def test_source_archive_rejects_member_count_and_size_caps(self) -> None:
        """소스 아카이브 거부 멤버 개수 및 크기 상한 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-source-archive-cap-test-") as tmp:
            tmp_path = Path(tmp)
            member_archive = tmp_path / "too-many.zip"
            with zipfile.ZipFile(member_archive, "w") as output:
                output.writestr("package/problems/alpha/problem.json", "{}")
                output.writestr("package/problems/beta/problem.json", "{}")
            member_out = tmp_path / "out-members"
            with (
                patch("judge.core.security_limits.MAX_ARCHIVE_MEMBERS", 1),
                self.assertRaisesRegex(JudgeError, "too many members"),
            ):
                safe_extract_zip(member_archive, member_out)
            self.assertFalse(member_out.exists())

            size_archive = tmp_path / "too-large.zip"
            with zipfile.ZipFile(size_archive, "w") as output:
                output.writestr("package/problems/alpha/problem.json", "{}")
            size_out = tmp_path / "out-size"
            with (
                patch("judge.core.security_limits.MAX_ARCHIVE_FILE_BYTES", 1),
                self.assertRaisesRegex(JudgeError, "member exceeds size limit"),
            ):
                safe_extract_zip(size_archive, size_out)
            self.assertFalse(size_out.exists())

            total_archive = tmp_path / "too-much-total.zip"
            with zipfile.ZipFile(total_archive, "w") as output:
                output.writestr("package/problems/alpha/problem.json", "{}")
                output.writestr("package/problems/alpha/notes.txt", "abcd")
            total_out = tmp_path / "out-total"
            with (
                patch("judge.core.security_limits.MAX_ARCHIVE_TOTAL_BYTES", 3),
                self.assertRaisesRegex(JudgeError, "extracted size exceeds limit"),
            ):
                safe_extract_zip(total_archive, total_out)
            self.assertFalse(total_out.exists())

    def test_github_download_falls_back_to_source_archive_without_pack_asset(self) -> None:
        """GitHub 다운로드 대체 복귀 소스 아카이브 없이 패키지 자산 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""

        def fake_github_json(url: str) -> dict:
            """실제 GitHub JSON 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

            Args:
                url (str): 응답 준비 상태를 확인할 HTTP 주소입니다.

            Returns:
                dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
            """
            if url.endswith("/releases/latest"):
                raise JudgeError("GitHub request failed: HTTP 404")
            if url.endswith("/commits/main"):
                return {"sha": "abc123"}
            return {"default_branch": "main"}

        with (
            patch("judge.core.remote_install.github_json", side_effect=fake_github_json),
            patch("judge.core.remote_install.github_default_branch", return_value="main"),
            patch("judge.core.remote_install.github_commit_sha", return_value="abc123"),
            patch("judge.core.remote_install.download_asset") as download_asset,
            patch("judge.core.remote_install.install_problem_source_archive") as install_archive,
        ):
            install_archive.return_value = {
                "installedPath": "/tmp/source",
                "label": "source",
                "installType": "source",
            }

            result = download_problem_pack_from_github("tony9402/algorithm-package")

        self.assertEqual(result["installType"], "source")
        download_asset.assert_called_once()
        self.assertEqual(
            install_archive.call_args.kwargs["repository"],
            "tony9402/algorithm-package",
        )
        self.assertEqual(install_archive.call_args.kwargs["ref"], "main")
        self.assertEqual(install_archive.call_args.kwargs["commit_sha"], "abc123")

    def test_github_pack_download_requires_trusted_repository(self) -> None:
        """GitHub 패키지 다운로드 요구 신뢰된 저장소 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-untrusted-repo-test-") as tmp:
            with patch.dict(os.environ, {"ALJ_DATA_HOME": str(Path(tmp) / "data")}, clear=True):
                with (
                    patch("judge.core.remote_install.github_json") as github_json,
                    self.assertRaisesRegex(JudgeError, "untrusted repository"),
                ):
                    download_problem_pack_from_github("other/problems")

        github_json.assert_not_called()

    def test_github_pack_download_verifies_release_checksum(self) -> None:
        """GitHub 패키지 다운로드 검증 릴리스 체크섬 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        assets = [
            {
                "name": "basic-1-macos-arm64.aljpack",
                "browser_download_url": "https://example.com/basic.aljpack",
            },
            {
                "name": "basic-1-macos-arm64.aljpack.sha256",
                "browser_download_url": "https://example.com/basic.aljpack.sha256",
            },
        ]

        def fake_download(url: str, target: Path) -> None:
            """실제 다운로드 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

            Args:
                url (str): 응답 준비 상태를 확인할 HTTP 주소입니다.
                target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.
            """
            if url.endswith(".aljpack"):
                create_minimal_pack(target)
                return
            target.write_text(
                f"{sha256_file(target.with_name('basic-1-macos-arm64.aljpack'))}  "
                "basic-1-macos-arm64.aljpack\n",
                encoding="utf-8",
            )

        with tempfile.TemporaryDirectory(prefix="alj-remote-pack-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "judge.core.remote_install.github_json",
                    return_value={"assets": assets},
                ),
                patch("judge.core.remote_install.download_asset", side_effect=fake_download),
                patch(
                    "judge.core.remote_install.install_downloaded_problem_pack",
                    return_value={"installedPath": "/tmp/pack", "installType": "pack"},
                ) as install_pack,
            ):
                result = download_problem_pack_from_github("tony9402/algorithm-package")

        self.assertTrue(result["trustedRepository"])
        self.assertTrue(result["checksumVerified"])
        self.assertEqual(result["checksumSource"], "basic-1-macos-arm64.aljpack.sha256")
        install_pack.assert_called_once()

    def test_github_pack_download_rejects_missing_or_mismatched_checksum(self) -> None:
        """GitHub 패키지 다운로드 거부 누락 또는 불일치 체크섬 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        pack_asset = {
            "name": "basic-1-macos-arm64.aljpack",
            "browser_download_url": "https://example.com/basic.aljpack",
        }
        checksum_asset = {
            "name": "basic-1-macos-arm64.aljpack.sha256",
            "browser_download_url": "https://example.com/basic.aljpack.sha256",
        }

        with tempfile.TemporaryDirectory(prefix="alj-remote-pack-test-") as tmp:
            env = {
                **os.environ,
                "ALJ_DATA_HOME": str(Path(tmp) / "data"),
                "ALJ_CACHE_HOME": str(Path(tmp) / "cache"),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "judge.core.remote_install.github_json",
                    return_value={"assets": [pack_asset]},
                ),
                patch("judge.core.remote_install.download_asset") as download_asset,
                patch("judge.core.remote_install.install_downloaded_problem_pack") as install_pack,
                self.assertRaisesRegex(JudgeError, "no checksum asset"),
            ):
                download_problem_pack_from_github("tony9402/algorithm-package")
            download_asset.assert_not_called()
            install_pack.assert_not_called()

            def mismatched_download(url: str, target: Path) -> None:
                """불일치 다운로드 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Args:
                    url (str): 응답 준비 상태를 확인할 HTTP 주소입니다.
                    target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.
                """
                if url.endswith(".aljpack"):
                    create_minimal_pack(target)
                    return
                target.write_text(
                    f"{'0' * 64}  basic-1-macos-arm64.aljpack\n",
                    encoding="utf-8",
                )

            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "judge.core.remote_install.github_json",
                    return_value={"assets": [pack_asset, checksum_asset]},
                ),
                patch("judge.core.remote_install.download_asset", side_effect=mismatched_download),
                patch("judge.core.remote_install.install_downloaded_problem_pack") as install_pack,
                self.assertRaisesRegex(JudgeError, "checksum mismatch"),
            ):
                download_problem_pack_from_github("tony9402/algorithm-package")
            install_pack.assert_not_called()

    def test_direct_pack_download_requires_checksum_and_verifies_match(self) -> None:
        """직접 패키지 다운로드 요구 체크섬 및 검증 일치 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        pack_bytes = b"pack-bytes"
        digest = hashlib.sha256(pack_bytes).hexdigest()

        def fake_download_missing_sidecar(url: str, target: Path) -> None:
            """실제 다운로드 누락 동반 파일 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

            Args:
                url (str): 응답 준비 상태를 확인할 HTTP 주소입니다.
                target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.
            """
            if url.endswith(".sha256"):
                raise JudgeError("problem pack download failed: HTTP 404")
            target.write_bytes(pack_bytes)

        with tempfile.TemporaryDirectory(prefix="alj-direct-pack-test-") as tmp:
            env = {"ALJ_CACHE_HOME": str(Path(tmp) / "cache")}
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "judge.core.remote_install.download_asset",
                    side_effect=fake_download_missing_sidecar,
                ),
                patch("judge.core.remote_install.install_downloaded_problem_pack") as install_pack,
                self.assertRaisesRegex(JudgeError, "requires --checksum"),
            ):
                download_problem_pack_from_url("https://example.com/basic.aljpack")
            install_pack.assert_not_called()

            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "judge.core.remote_install.download_asset",
                    side_effect=fake_download_missing_sidecar,
                ),
                patch(
                    "judge.core.remote_install.install_downloaded_problem_pack",
                    return_value={"installedPath": "/tmp/basic", "installType": "pack"},
                ) as install_pack,
            ):
                result = download_problem_pack_from_url(
                    "https://example.com/basic.aljpack",
                    checksum=digest,
                )
            self.assertTrue(result["checksumVerified"])
            self.assertEqual(result["checksumSha256"], digest)
            install_pack.assert_called_once()

            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "judge.core.remote_install.download_asset",
                    side_effect=fake_download_missing_sidecar,
                ),
                patch("judge.core.remote_install.install_downloaded_problem_pack") as install_pack,
                self.assertRaisesRegex(JudgeError, "checksum mismatch"),
            ):
                download_problem_pack_from_url(
                    "https://example.com/basic.aljpack",
                    checksum="0" * 64,
                )
            install_pack.assert_not_called()

    def test_direct_pack_download_uses_checksum_url_or_auto_sidecar(self) -> None:
        """직접 패키지 다운로드 사용 체크섬 주소 또는 자동 동반 파일 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        pack_bytes = b"pack-bytes"
        digest = hashlib.sha256(pack_bytes).hexdigest()

        def fake_download(url: str, target: Path) -> None:
            """실제 다운로드 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

            Args:
                url (str): 응답 준비 상태를 확인할 HTTP 주소입니다.
                target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.
            """
            if url.endswith(".aljpack"):
                target.write_bytes(pack_bytes)
                return
            target.write_text(f"{digest}  basic.aljpack\n", encoding="utf-8")

        with tempfile.TemporaryDirectory(prefix="alj-direct-pack-test-") as tmp:
            env = {"ALJ_CACHE_HOME": str(Path(tmp) / "cache")}
            with (
                patch.dict(os.environ, env, clear=True),
                patch("judge.core.remote_install.download_asset", side_effect=fake_download),
                patch(
                    "judge.core.remote_install.install_downloaded_problem_pack",
                    return_value={"installedPath": "/tmp/basic", "installType": "pack"},
                ),
            ):
                explicit = download_problem_pack_from_url(
                    "https://example.com/basic.aljpack",
                    checksum_url="https://example.com/checksums.txt",
                )
                automatic = download_problem_pack_from_url("https://example.com/basic.aljpack")

        self.assertEqual(explicit["checksumSha256"], digest)
        self.assertEqual(automatic["checksumSha256"], digest)

    def test_download_asset_enforces_content_length_and_streaming_cap(self) -> None:
        """다운로드 자산 강제 콘텐츠 길이 및 스트리밍 상한 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""

        class FakeResponse(io.BytesIO):
            """응답 테스트 지원에 필요한 상태와 동작을 함께 제공하는 클래스입니다."""

            def __init__(self, payload: bytes, headers: dict[str, str]) -> None:
                """테스트용 난수 대역이 순환 반환할 값을 초기화합니다.

                Args:
                    payload (bytes): 페이로드 값을 지정하는 인자입니다.
                    headers (dict[str, str]): 헤더 값을 지정하는 인자입니다.
                """
                super().__init__(payload)
                self.headers = headers

            def __enter__(self) -> FakeResponse:
                """시작 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Returns:
                    FakeResponse: 호출자가 다음 검증 단계에서 사용할 결과 값입니다.
                """
                return self

            def __exit__(self, *args) -> None:
                """종료 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Args:
                    args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                """
                self.close()

        with tempfile.TemporaryDirectory(prefix="alj-download-cap-test-") as tmp:
            target = Path(tmp) / "asset.aljpack"
            with (
                patch(
                    "judge.core.remote_github.urlopen",
                    return_value=FakeResponse(b"", {"Content-Length": "10"}),
                ),
                self.assertRaisesRegex(LimitExceededError, "remote download exceeds"),
            ):
                download_asset("https://example.com/basic.aljpack", target, limit_bytes=5)
            self.assertFalse(target.exists())

            with (
                patch(
                    "judge.core.remote_github.urlopen",
                    return_value=FakeResponse(b"abcdef", {}),
                ),
                self.assertRaisesRegex(LimitExceededError, "remote download exceeds"),
            ):
                download_asset("https://example.com/basic.aljpack", target, limit_bytes=5)
            self.assertFalse(target.exists())

    def test_download_asset_uses_certifi_or_custom_ca_bundle_context(self) -> None:
        """다운로드 자산 사용 certifi 또는 사용자 지정 CA 번들 맥락 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""

        class FakeResponse(io.BytesIO):
            """응답 테스트 지원에 필요한 상태와 동작을 함께 제공하는 클래스입니다."""

            def __init__(self) -> None:
                """테스트용 난수 대역이 순환 반환할 값을 초기화합니다."""
                super().__init__(b"pack")
                self.headers = {"Content-Length": "4"}

            def __enter__(self) -> FakeResponse:
                """시작 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Returns:
                    FakeResponse: 호출자가 다음 검증 단계에서 사용할 결과 값입니다.
                """
                return self

            def __exit__(self, *args) -> None:
                """종료 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

                Args:
                    args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                """
                self.close()

        with tempfile.TemporaryDirectory(prefix="alj-download-ca-test-") as tmp:
            target = Path(tmp) / "asset.aljpack"
            context = object()
            captured: dict[str, object] = {}

            def fake_urlopen(request, *, timeout, context):
                """실제 urlopen 경로를 대체해 외부 도구 없이도 성공, 실패, 진행 로그를 결정적으로 재현합니다.

                Args:
                    request (Any): 요청 값을 지정하는 인자입니다.
                    timeout (Any): 조건이 만족될 때까지 기다릴 최대 시간입니다.
                    context (Any): 맥락 값을 지정하는 키워드 인자입니다.

                Returns:
                    Any: 테스트 대상 API가 실제 실행 결과처럼 소비할 수 있는 결정적 결과 데이터입니다.
                """
                captured["timeout"] = timeout
                captured["context"] = context
                return FakeResponse()

            with (
                patch.dict(
                    os.environ, {"ALJ_CA_BUNDLE": str(Path(tmp) / "school-ca.pem")}, clear=True
                ),
                patch(
                    "judge.core.remote_github.ssl.create_default_context", return_value=context
                ) as create_context,
                patch("judge.core.remote_github.urlopen", side_effect=fake_urlopen),
            ):
                download_asset("https://example.com/basic.aljpack", target)

            create_context.assert_called_once_with(cafile=str(Path(tmp) / "school-ca.pem"))
            self.assertIs(captured["context"], context)
            self.assertEqual(target.read_bytes(), b"pack")

            target.unlink()
            with (
                patch.dict(os.environ, {}, clear=True),
                patch(
                    "judge.core.remote_github.certifi.where", return_value="/certifi/cacert.pem"
                ),
                patch(
                    "judge.core.remote_github.ssl.create_default_context", return_value=context
                ) as create_context,
                patch("judge.core.remote_github.urlopen", side_effect=fake_urlopen),
            ):
                download_asset("https://example.com/basic.aljpack", target)

            create_context.assert_called_once_with(cafile="/certifi/cacert.pem")

    def test_download_asset_ssl_certificate_failure_has_actionable_guidance(self) -> None:
        """다운로드 자산 SSL 인증서 실패 보유 조치 가능한 안내 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-download-ssl-test-") as tmp:
            target = Path(tmp) / "asset.aljpack"
            reason = ssl.SSLCertVerificationError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
            )
            with patch("judge.core.remote_github.urlopen", side_effect=URLError(reason)):
                with self.assertRaisesRegex(JudgeError, "HTTPS download, not git") as raised:
                    download_asset("https://example.com/basic.aljpack", target)

            self.assertIn("ALJ_CA_BUNDLE", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
