"""Managed toolchain manifest, installation, rollback, and resolver contracts."""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from alj_core.errors import JudgeError
from alj_core.paths import current_platform_id
from alj_core.toolchain_manifest import parse_toolchain_manifest
from alj_core.toolchains import (
    active_toolchain,
    deactivate_managed_toolchain,
    ensure_managed_toolchain,
    install_toolchain_from_local_archive,
    resolve_tool_details,
)
from judge.commands.doctor import resolved_tool_status
from judge.core.compiler_common import resolve_tool

TOOL_FILES = {
    "cxx": "bin/g++",
    "javac": "bin/javac",
    "java": "bin/java",
    "python": "bin/python3",
    "pypy": "bin/pypy3",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_fixture(
    root: Path,
    version: str = "1.0.0",
    *,
    provider_configured: bool = True,
) -> tuple[object, Path]:
    payload = root / f"payload-{version}"
    tools = {}
    for tool_id, relative in TOOL_FILES.items():
        executable = payload / relative
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text(f"#!/bin/sh\necho {tool_id}-{version}\n", encoding="utf-8")
        executable.chmod(0o755)
        tools[tool_id] = {"path": relative, "sha256": sha256(executable)}
    archive = root / f"toolchain-{version}.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        for path in sorted(payload.rglob("*")):
            output.add(path, arcname=path.relative_to(payload))
    manifest = parse_toolchain_manifest(
        {
            "schemaVersion": 1,
            "profileId": "test-fixture",
            "version": version,
            "platformId": current_platform_id(),
            "artifact": {
                "url": "https://fixtures.invalid/toolchain.tar.gz"
                if provider_configured
                else None,
                "sha256": sha256(archive),
                "signature": {"type": "test", "value": "fixture-only"}
                if provider_configured
                else None,
            },
            "license": {
                "name": "Test fixture license" if provider_configured else None,
                "url": "https://fixtures.invalid/license" if provider_configured else None,
            },
            "tools": tools,
        }
    )
    return manifest, archive


class ToolchainManifestTest(unittest.TestCase):
    def test_schema_file_and_model_are_versioned(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "packaging"
            / "toolchains"
            / "toolchain-manifest.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)
        self.assertEqual(
            set(schema["properties"]["tools"]["required"]),
            set(TOOL_FILES),
        )

    def test_manifest_rejects_tool_path_escape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-toolchain-") as tmp:
            manifest, _ = create_fixture(Path(tmp))
            payload = manifest.to_dict()
            payload["tools"]["cxx"]["path"] = "../g++"
            with self.assertRaisesRegex(JudgeError, "stay inside"):
                parse_toolchain_manifest(payload)


class ToolchainInstallTest(unittest.TestCase):
    def test_hash_verified_install_and_atomic_active_pointer(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-toolchain-") as tmp:
            root = Path(tmp)
            manifest, archive = create_fixture(root)
            managed_root = root / "managed"
            result = install_toolchain_from_local_archive(
                manifest,
                archive,
                root=managed_root,
            )

            self.assertFalse(result.reused)
            active = active_toolchain(managed_root)
            self.assertIsNotNone(active)
            self.assertEqual(active[0].version, "1.0.0")
            self.assertFalse(list(managed_root.glob(".active.json.*")))

    def test_modified_artifact_fails_before_active_pointer_change(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-toolchain-") as tmp:
            root = Path(tmp)
            manifest, archive = create_fixture(root)
            archive.write_bytes(archive.read_bytes() + b"tampered")
            managed_root = root / "managed"

            with self.assertRaisesRegex(JudgeError, "artifact hash mismatch"):
                install_toolchain_from_local_archive(manifest, archive, root=managed_root)
            self.assertFalse((managed_root / "active.json").exists())

    def test_same_manifest_rerun_does_not_download(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-toolchain-") as tmp:
            root = Path(tmp)
            manifest, archive = create_fixture(root)
            managed_root = root / "managed"
            downloader = Mock(return_value=archive)

            first = ensure_managed_toolchain(
                manifest,
                downloader=downloader,
                root=managed_root,
            )
            second = ensure_managed_toolchain(
                manifest,
                downloader=downloader,
                root=managed_root,
            )

            self.assertTrue(first.downloaded)
            self.assertTrue(second.reused)
            self.assertFalse(second.downloaded)
            downloader.assert_called_once_with("https://fixtures.invalid/toolchain.tar.gz")

    def test_unconfigured_provider_fails_closed_without_downloader(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-toolchain-") as tmp:
            root = Path(tmp)
            manifest, _ = create_fixture(root, provider_configured=False)
            downloader = Mock()
            with self.assertRaisesRegex(JudgeError, "provider is not configured"):
                ensure_managed_toolchain(
                    manifest,
                    downloader=downloader,
                    root=root / "managed",
                )
            downloader.assert_not_called()

    def test_active_pointer_failure_rolls_back_new_profile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-toolchain-") as tmp:
            root = Path(tmp)
            first_manifest, first_archive = create_fixture(root, "1.0.0")
            second_manifest, second_archive = create_fixture(root, "2.0.0")
            managed_root = root / "managed"
            install_toolchain_from_local_archive(
                first_manifest,
                first_archive,
                root=managed_root,
            )

            with (
                patch(
                    "alj_core.toolchains._write_active_pointer",
                    side_effect=OSError("simulated pointer failure"),
                ),
                self.assertRaisesRegex(OSError, "simulated pointer failure"),
            ):
                install_toolchain_from_local_archive(
                    second_manifest,
                    second_archive,
                    root=managed_root,
                )

            active = active_toolchain(managed_root)
            self.assertEqual(active[0].version, "1.0.0")
            self.assertFalse((managed_root / "profiles" / "test-fixture" / "2.0.0").exists())


class ToolchainResolverTest(unittest.TestCase):
    def test_priority_is_override_then_managed_then_validated_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-toolchain-") as tmp:
            root = Path(tmp)
            manifest, archive = create_fixture(root)
            managed_root = root / "managed"
            install_toolchain_from_local_archive(manifest, archive, root=managed_root)
            external = root / "override-g++"
            external.write_text("#!/bin/sh\n", encoding="utf-8")
            external.chmod(0o755)
            path_bin = root / "path-bin"
            path_bin.mkdir()
            path_cxx = path_bin / "g++"
            path_cxx.write_text("#!/bin/sh\n", encoding="utf-8")
            path_cxx.chmod(0o755)

            with patch.dict(
                os.environ,
                {"ALJ_CXX": str(external), "PATH": str(path_bin)},
                clear=False,
            ):
                resolved = resolve_tool_details("cxx", root=managed_root)
                self.assertEqual(resolved.source, "override")
                self.assertEqual(Path(resolved.path), external.resolve())

            with patch.dict(
                os.environ,
                {"ALJ_CXX": "", "PATH": str(path_bin)},
                clear=False,
            ):
                resolved = resolve_tool_details("cxx", root=managed_root)
                self.assertEqual(resolved.source, "managed")
                self.assertEqual(resolved.profile_id, "test-fixture")
                deactivate_managed_toolchain(managed_root)
                resolved = resolve_tool_details("cxx", root=managed_root)
                self.assertEqual(resolved.source, "path")
                self.assertEqual(Path(resolved.path), path_cxx.resolve())

    def test_invalid_override_does_not_fall_through(self) -> None:
        with patch.dict(os.environ, {"ALJ_CXX": "/missing/alj/g++"}, clear=False):
            with self.assertRaisesRegex(JudgeError, "not executable"):
                resolve_tool_details("cxx")

    def test_doctor_and_compiler_resolve_the_same_executable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-toolchain-") as tmp:
            root = Path(tmp)
            manifest, archive = create_fixture(root)
            managed_root = root / "managed"
            install_toolchain_from_local_archive(manifest, archive, root=managed_root)
            with patch.dict(
                os.environ,
                {"ALJ_TOOLCHAIN_HOME": str(managed_root), "ALJ_CXX": ""},
                clear=False,
            ):
                doctor = resolved_tool_status("C++ compiler", "cxx", "cpp")
                compiler = resolve_tool("ALJ_CXX", ["g++"])

            self.assertEqual(doctor["status"], "ok")
            self.assertEqual(doctor["source"], "managed")
            self.assertEqual(doctor["path"], compiler)


if __name__ == "__main__":
    unittest.main()
