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
    """Tests for easy problem installation helpers."""

    def test_github_repository_from_source_accepts_common_forms(self) -> None:
        """Repository input should work with owner/name, HTTPS, and SSH forms."""
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
        """The official install source should default to algorithm-package."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(official_pack_repository(), "tony9402/algorithm-package")

    def test_github_repository_from_source_rejects_non_github_source(self) -> None:
        """Non-GitHub strings should be left for other installers to handle."""
        self.assertIsNone(github_repository_from_source("not a repository"))
        self.assertIsNone(github_repository_from_source("https://example.com/owner/repo"))

    def test_select_pack_asset_prefers_requested_asset(self) -> None:
        """Explicit asset names should pick the matching .aljpack asset."""
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
        """Missing release pack assets should be reported clearly."""
        with self.assertRaises(JudgeError):
            select_pack_asset([{"name": "notes.txt"}], None)

    def test_trusted_repository_policy_uses_default_owner_and_user_allowlist(self) -> None:
        """Only the official repository and explicitly added repositories should be trusted."""
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
        """A source package with problems/ should install into the problem search path."""
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
        """Source archives must not be allowed to escape extraction directories."""
        with tempfile.TemporaryDirectory(prefix="alj-source-archive-test-") as tmp:
            archive = Path(tmp) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../escaped.txt", "bad")

            with self.assertRaises(JudgeError):
                install_problem_source_archive(archive, repository="owner/repo", ref="main")

    def test_source_archive_rejects_symlink_member(self) -> None:
        """Source zip archives must not install Unix symlink entries."""
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
        """Source zip archives should enforce extraction resource caps before install."""
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
        """Repositories without .aljpack release assets should install source packages."""

        def fake_github_json(url: str) -> dict:
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
        """Remote GitHub installs should reject repositories outside the trust policy."""
        with tempfile.TemporaryDirectory(prefix="alj-untrusted-repo-test-") as tmp:
            with patch.dict(os.environ, {"ALJ_DATA_HOME": str(Path(tmp) / "data")}, clear=True):
                with (
                    patch("judge.core.remote_install.github_json") as github_json,
                    self.assertRaisesRegex(JudgeError, "untrusted repository"),
                ):
                    download_problem_pack_from_github("other/problems")

        github_json.assert_not_called()

    def test_github_pack_download_verifies_release_checksum(self) -> None:
        """Trusted .aljpack release assets should verify their sidecar checksum."""
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
        """Checksum absence or mismatch should fail instead of falling back silently."""
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
        """Direct .aljpack URLs should not install without a verifiable checksum."""
        pack_bytes = b"pack-bytes"
        digest = hashlib.sha256(pack_bytes).hexdigest()

        def fake_download_missing_sidecar(url: str, target: Path) -> None:
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
        """Direct .aljpack URLs should accept explicit or automatic checksum sidecars."""
        pack_bytes = b"pack-bytes"
        digest = hashlib.sha256(pack_bytes).hexdigest()

        def fake_download(url: str, target: Path) -> None:
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
        """Remote downloads should reject oversized responses and remove partial files."""

        class FakeResponse(io.BytesIO):
            def __init__(self, payload: bytes, headers: dict[str, str]) -> None:
                super().__init__(payload)
                self.headers = headers

            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args) -> None:
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
        """HTTPS downloads should use a verifying CA bundle context."""

        class FakeResponse(io.BytesIO):
            def __init__(self) -> None:
                super().__init__(b"pack")
                self.headers = {"Content-Length": "4"}

            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args) -> None:
                self.close()

        with tempfile.TemporaryDirectory(prefix="alj-download-ca-test-") as tmp:
            target = Path(tmp) / "asset.aljpack"
            context = object()
            captured: dict[str, object] = {}

            def fake_urlopen(request, *, timeout, context):
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
        """Certificate verification failures should explain the HTTPS/CA-bundle fix."""
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
