from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.build_rpm import (
    render_main_spec,
    render_release_spec,
    render_repo_file,
    stage_rpmbuild_tree,
    validate_rpm_platform,
    validate_rpm_version,
)


def standalone_archive(path: Path) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name in ("judge", "problem-studio"):
            payload = b"#!/bin/sh\n"
            info = tarfile.TarInfo(f"algorithm-local-judge/bin/{name}")
            info.mode = 0o755
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return path


class RpmBuilderTest(unittest.TestCase):
    def test_application_spec_installs_both_launchers_without_owning_user_data(self) -> None:
        spec = render_main_spec("1.2.3", "algorithm-local-judge.tar.gz")

        self.assertIn("Version:        1.2.3", spec)
        self.assertIn("/usr/bin/judge", spec)
        self.assertIn("/usr/bin/problem-studio", spec)
        self.assertIn("/opt/algorithm-local-judge", spec)
        self.assertNotIn(".local/share", spec)
        self.assertNotIn("%postun", spec)

    def test_release_rpm_enables_signed_repository_without_plugin_prerequisite(self) -> None:
        spec = render_release_spec("1.2.3")
        repository = render_repo_file(
            "https://packages.example.test/rpm/$releasever/$basearch",
            "https://packages.example.test/keys/rpm.gpg",
        )

        self.assertIn("BuildArch:      noarch", spec)
        self.assertIn("%config(noreplace)", spec)
        self.assertIn("gpgcheck=1", repository)
        self.assertIn("repo_gpgcheck=1", repository)
        self.assertNotIn("config-manager", repository)

    def test_rpmbuild_staging_contains_two_specs_and_immutable_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-rpm-test-") as tmp:
            root = Path(tmp)
            archive = standalone_archive(root / "standalone.tar.gz")
            topdir = root / "rpmbuild"

            specs = stage_rpmbuild_tree(
                archive,
                topdir,
                "1.2.3",
                "https://packages.example.test/rpm/$releasever/$basearch",
                "https://packages.example.test/keys/rpm.gpg",
            )

            self.assertEqual(
                {path.name for path in specs},
                {
                    "algorithm-local-judge.spec",
                    "alj-release.spec",
                },
            )
            self.assertTrue((topdir / "SOURCES" / archive.name).is_file())
            self.assertTrue((topdir / "SOURCES" / "algorithm-local-judge.repo").is_file())

    def test_rpm_platform_contract_fails_fast(self) -> None:
        validate_rpm_platform("linux-amd64", "linux-amd64")
        with self.assertRaisesRegex(ValueError, "unsupported RPM platform"):
            validate_rpm_platform("linux-arm64", "linux-amd64")
        with self.assertRaisesRegex(ValueError, "require a linux-amd64 host"):
            validate_rpm_platform("linux-amd64", "macos-arm64")

    def test_rpm_version_and_repository_inputs_fail_closed(self) -> None:
        validate_rpm_version("1.2.3")
        with self.assertRaisesRegex(ValueError, "must be numeric"):
            validate_rpm_version("1.2.3-beta")
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            render_repo_file(
                "http://packages.example.test/rpm",
                "https://packages.example.test/key.gpg",
            )


if __name__ == "__main__":
    unittest.main()
