"""Immutable release manifest and stable publication gate contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from judge.core.errors import JudgeError
from scripts.build_native_signing_plan import main as signing_plan_main
from scripts.build_native_signing_plan import signing_plan
from scripts.build_release_manifest import build_manifest
from scripts.build_winget_manifest import manifest_payloads, write_manifests
from scripts.validate_release_manifest import (
    validate_release_manifest,
    validate_stable_package_assets,
)
from tests.test_release_scanner import ReleaseScannerTest

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_sidecars(path: Path) -> None:
    path.with_name(f"{path.name}.sha256").write_text(
        f"{sha256(path)}  {path.name}\n",
        encoding="utf-8",
    )
    path.with_name(f"{path.name}.sigstore.json").write_text(
        json.dumps(
            {
                "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                "verificationMaterial": {},
                "messageSignature": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )


def fixture_args(root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        assets=root,
        output=root / "release-manifest.json",
        version="0.1.0",
        tag="v0.1.0",
        channel="candidate",
        source_commit="local-candidate",
        required_platform=["macos-arm64"],
        signing_plan=None,
        official_pack_repository="",
        official_pack_ref="",
        official_pack_asset="",
        official_pack_sha256="",
        official_pack_signature="",
    )


def create_release_fixture(root: Path) -> tuple[dict[str, object], Path]:
    archive = ReleaseScannerTest().make_standalone_archive(root)
    write_sidecars(archive)
    package = root / "algorithm-local-judge-0.1.0-macos-arm64.pkg"
    package.write_bytes(b"unsigned-macos-pkg-candidate")
    write_sidecars(package)
    sbom = root / "algorithm-local-judge.cdx.json"
    sbom.write_text(
        json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.6"}) + "\n",
        encoding="utf-8",
    )
    write_sidecars(sbom)
    manifest = build_manifest(fixture_args(root))
    manifest_path = root / "release-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest, manifest_path


class ReleaseManifestTest(unittest.TestCase):
    def test_schema_and_candidate_validate_all_local_assets(self) -> None:
        schema = json.loads(
            (ROOT / "packaging" / "release-manifest.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)
        artifact_kinds = schema["$defs"]["artifact"]["properties"]["kind"]["enum"]
        self.assertIn("winget-manifest", artifact_kinds)
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            _, manifest_path = create_release_fixture(root)

            payload = validate_release_manifest(manifest_path, root)

            self.assertEqual(payload["artifacts"][0]["launchers"], ["judge", "problem-studio"])
            self.assertEqual(payload["sbom"]["format"], "CycloneDX")

    def test_missing_signature_sidecar_fails_manifest_generation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            archive = ReleaseScannerTest().make_standalone_archive(root)
            archive.with_name(f"{archive.name}.sha256").write_text(
                f"{sha256(archive)}  {archive.name}\n",
                encoding="utf-8",
            )
            sbom = root / "algorithm-local-judge.cdx.json"
            sbom.write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
            write_sidecars(sbom)

            with self.assertRaisesRegex(JudgeError, "sidecar is missing"):
                build_manifest(fixture_args(root))

    def test_stable_rejects_unverified_native_signing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            manifest, manifest_path = create_release_fixture(root)
            manifest["release"].update({"channel": "stable", "sourceCommit": "b" * 40})
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "native signing is not verified"):
                validate_release_manifest(manifest_path, root, stable=True)

    def test_stable_allows_external_official_pack_to_be_unconfigured(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            manifest, manifest_path = create_release_fixture(root)
            manifest["release"].update({"channel": "stable", "sourceCommit": "b" * 40})
            manifest["artifacts"][0]["nativeSigning"] = {
                "type": "developer-id",
                "status": "verified",
                "attestation": "notary-log-fixture",
            }
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            validate_release_manifest(manifest_path, root, stable=True)

    def test_stable_supports_signed_standalone_only_release(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            source = ReleaseScannerTest().make_standalone_archive(root)
            for platform in ("macos-arm64", "macos-amd64", "linux-amd64", "windows-amd64"):
                archive = root / f"algorithm-local-judge-0.1.0-{platform}.tar.gz"
                if archive != source:
                    archive.write_bytes(source.read_bytes())
                write_sidecars(archive)
            sbom = root / "algorithm-local-judge.cdx.json"
            sbom.write_text(
                json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.6"}) + "\n",
                encoding="utf-8",
            )
            write_sidecars(sbom)
            args = fixture_args(root)
            args.channel = "stable"
            args.source_commit = "b" * 40
            args.required_platform = [
                "macos-arm64",
                "macos-amd64",
                "linux-amd64",
                "windows-amd64",
            ]
            manifest = build_manifest(args)
            manifest_path = root / "release-manifest.json"
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            validate_release_manifest(manifest_path, root, stable=True)

    def test_stable_rejects_partial_official_pack_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            manifest, manifest_path = create_release_fixture(root)
            manifest["release"].update({"channel": "stable", "sourceCommit": "b" * 40})
            manifest["artifacts"][0]["nativeSigning"] = {
                "type": "developer-id",
                "status": "verified",
                "attestation": "notary-log-fixture",
            }
            manifest["officialPack"]["repository"] = "fixture/official-pack"
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "official pack reference is incomplete"):
                validate_release_manifest(manifest_path, root, stable=True)

    def test_complete_stable_fixture_requires_manifest_sidecars(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            manifest, manifest_path = create_release_fixture(root)
            manifest["release"].update({"channel": "stable", "sourceCommit": "b" * 40})
            manifest["artifacts"][0]["nativeSigning"] = {
                "type": "developer-id",
                "status": "verified",
                "attestation": "notary-log-fixture",
            }
            manifest["officialPack"] = {
                "status": "configured",
                "repository": "fixture/official-pack",
                "ref": "c" * 40,
                "asset": "official.aljpack",
                "sha256": "d" * 64,
                "signature": "official.aljpack.sigstore.json",
            }
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "sidecars are missing"):
                validate_release_manifest(
                    manifest_path,
                    root,
                    stable=True,
                    require_manifest_sidecars=True,
                )
            write_sidecars(manifest_path)
            validate_release_manifest(
                manifest_path,
                root,
                stable=True,
                require_manifest_sidecars=True,
            )

    def test_stable_rejects_moving_official_pack_ref(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            manifest, manifest_path = create_release_fixture(root)
            manifest["release"].update({"channel": "stable", "sourceCommit": "b" * 40})
            manifest["artifacts"][0]["nativeSigning"] = {
                "type": "developer-id",
                "status": "verified",
                "attestation": "notary-log-fixture",
            }
            manifest["officialPack"] = {
                "status": "configured",
                "repository": "fixture/official-pack",
                "ref": "latest",
                "asset": "official.aljpack",
                "sha256": "d" * 64,
                "signature": "official.aljpack.sigstore.json",
            }
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "immutable commit"):
                validate_release_manifest(manifest_path, root, stable=True)

    def test_availability_revalidation_detects_missing_sbom(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            _, manifest_path = create_release_fixture(root)
            (root / "algorithm-local-judge.cdx.json").unlink()

            with self.assertRaisesRegex(JudgeError, "SBOM is missing"):
                validate_release_manifest(manifest_path, root)

    def test_checksum_sidecar_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            manifest, manifest_path = create_release_fixture(root)
            checksum = root / manifest["artifacts"][0]["checksum"]["name"]
            checksum.write_text(f"{'0' * 64}  tampered\n", encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "checksum sidecar hash mismatch"):
                validate_release_manifest(manifest_path, root)

    def test_native_signing_plan_is_unconfigured_without_credentials(self) -> None:
        with patch("scripts.build_native_signing_plan.shutil.which", return_value=None):
            plan = signing_plan({})

        self.assertEqual(set(plan["targets"]), {"macos", "windows", "apt", "rpm"})
        for target in plan["targets"].values():
            self.assertEqual(target["status"], "unconfigured")
            self.assertTrue(target["missingCredentials"])
        self.assertEqual(plan["targets"]["macos"]["type"], "developer-id")
        self.assertEqual(plan["targets"]["windows"]["type"], "authenticode")
        self.assertEqual(plan["targets"]["apt"]["type"], "apt-gpg")
        self.assertEqual(plan["targets"]["rpm"]["type"], "rpm-gpg")

    def test_native_signing_builder_require_ready_fails_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-signing-plan-") as tmp:
            output = Path(tmp) / "plan.json"
            with (
                patch("scripts.build_native_signing_plan.shutil.which", return_value=None),
                patch(
                    "sys.argv",
                    ["build_native_signing_plan.py", "--output", str(output), "--require-ready"],
                ),
            ):
                self.assertEqual(signing_plan_main(), 1)
            self.assertTrue(output.is_file())

    def test_native_signing_evidence_is_scoped_to_a_hash_pinned_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-signing-evidence-") as tmp:
            root = Path(tmp)
            package = root / "algorithm-local-judge-0.1.0-macos-arm64.pkg"
            package.write_bytes(b"signed-notarized-package")
            evidence = root / f"{package.name}.native-signing.json"
            evidence.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "target": "macos",
                        "type": "developer-id",
                        "status": "verified",
                        "artifact": {"name": package.name, "sha256": sha256(package)},
                        "attestation": {
                            "provider": "apple-notarytool",
                            "submissionId": "fixture",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("scripts.build_native_signing_plan.shutil.which", return_value=None):
                plan = signing_plan({}, root)

            record = plan["targets"]["macos"]["artifacts"][package.name]
            self.assertEqual(record["status"], "verified")
            self.assertIn("apple-notarytool", record["attestation"])

            package.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                signing_plan({}, root)

    def test_release_manifest_maps_rpm_msi_and_winget_native_signing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            create_release_fixture(root)
            msi = root / "algorithm-local-judge-0.1.0-windows-amd64.msi"
            msi.write_bytes(b"unsigned-msi-candidate")
            rpm = root / "algorithm-local-judge-0.1.0-1.x86_64.rpm"
            rpm.write_bytes(b"unsigned-rpm-candidate")
            release_rpm = root / "alj-release-0.1.0-1.noarch.rpm"
            release_rpm.write_bytes(b"unsigned-release-rpm-candidate")
            for artifact in (msi, rpm, release_rpm):
                write_sidecars(artifact)
            payloads = manifest_payloads(
                msi,
                "Example.AlgorithmLocalJudge",
                "0.1.0",
                f"https://github.com/example/alj/releases/download/v0.1.0/{msi.name}",
            )
            manifests = write_manifests(
                payloads,
                root / "winget",
                "Example.AlgorithmLocalJudge",
            )
            for source in manifests:
                target = root / source.name
                target.write_bytes(source.read_bytes())
                write_sidecars(target)
            plan_path = root / "native-signing-plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "targets": {
                            "windows": {
                                "type": "authenticode",
                                "status": "verified",
                                "attestation": "windows-attestation",
                            },
                            "rpm": {
                                "type": "rpm-gpg",
                                "status": "verified",
                                "attestation": "rpm-attestation",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = fixture_args(root)
            args.signing_plan = plan_path

            manifest = build_manifest(args)
            records = {record["name"]: record for record in manifest["artifacts"]}

            self.assertEqual(records[msi.name]["nativeSigning"]["type"], "authenticode")
            self.assertEqual(records[rpm.name]["nativeSigning"]["type"], "rpm-gpg")
            for source in manifests:
                self.assertEqual(
                    records[source.name]["nativeSigning"],
                    {"type": "sigstore-only", "status": "verified", "attestation": None},
                )

    def test_winget_manifest_rejects_msi_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-release-manifest-") as tmp:
            root = Path(tmp)
            _, manifest_path = create_release_fixture(root)
            msi = root / "algorithm-local-judge-0.1.0-windows-amd64.msi"
            msi.write_bytes(b"unsigned-msi-candidate")
            write_sidecars(msi)
            payloads = manifest_payloads(
                msi,
                "Example.AlgorithmLocalJudge",
                "0.1.0",
                f"https://github.com/example/alj/releases/download/v0.1.0/{msi.name}",
            )
            payloads["installer"]["Installers"][0]["InstallerSha256"] = "0" * 64
            manifests = write_manifests(
                payloads,
                root / "winget",
                "Example.AlgorithmLocalJudge",
            )
            for source in manifests:
                target = root / source.name
                target.write_bytes(source.read_bytes())
                write_sidecars(target)
            args = fixture_args(root)
            manifest = build_manifest(args)
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "does not match the release MSI"):
                validate_release_manifest(manifest_path, root)

    def test_stable_package_contract_requires_linux_and_windows_installers(self) -> None:
        with self.assertRaisesRegex(JudgeError, "Debian package"):
            validate_stable_package_assets([], ["linux-amd64"])
        with self.assertRaisesRegex(JudgeError, "application RPM"):
            validate_stable_package_assets(
                [
                    {
                        "kind": "deb",
                        "name": "algorithm-local-judge_0.1.0_amd64.deb",
                    }
                ],
                ["linux-amd64"],
            )
        with self.assertRaisesRegex(JudgeError, "repository bootstrap RPM"):
            validate_stable_package_assets(
                [
                    {
                        "kind": "deb",
                        "name": "algorithm-local-judge_0.1.0_amd64.deb",
                    },
                    {
                        "kind": "rpm",
                        "name": "algorithm-local-judge-0.1.0-1.x86_64.rpm",
                    },
                ],
                ["linux-amd64"],
            )
        linux_without_apt = [
            {
                "kind": "deb",
                "name": "algorithm-local-judge_0.1.0_amd64.deb",
            },
            {
                "kind": "rpm",
                "name": "algorithm-local-judge-0.1.0-1.x86_64.rpm",
            },
            {"kind": "rpm", "name": "alj-release-0.1.0-1.noarch.rpm"},
        ]
        with self.assertRaisesRegex(JudgeError, "signed APT repository"):
            validate_stable_package_assets(linux_without_apt, ["linux-amd64"])
        with self.assertRaisesRegex(JudgeError, "APT bootstrap package"):
            validate_stable_package_assets(
                [
                    *linux_without_apt,
                    {
                        "kind": "apt-repository",
                        "name": "algorithm-local-judge-0.1.0-apt-repository.tar.gz",
                    },
                ],
                ["linux-amd64"],
            )
        with self.assertRaisesRegex(JudgeError, "WiX MSI"):
            validate_stable_package_assets([], ["windows-amd64"])
        with self.assertRaisesRegex(JudgeError, "WinGet manifests"):
            validate_stable_package_assets(
                [
                    {
                        "kind": "msi",
                        "name": "algorithm-local-judge-0.1.0-windows-amd64.msi",
                    }
                ],
                ["windows-amd64"],
            )
        with self.assertRaisesRegex(JudgeError, "macos-arm64 PKG"):
            validate_stable_package_assets([], ["macos-arm64"])


class ReleaseWorkflowContractTest(unittest.TestCase):
    def test_release_validation_scripts_support_direct_execution(self) -> None:
        for script in ("validate_release_manifest.py", "smoke_release_availability.py"):
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / script), "--help"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_stable_gate_precedes_publish_and_post_publish_smoke_follows(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        gate = workflow.index("validate_release_manifest.py")
        publish = workflow.index("gh release upload")
        smoke = workflow.index("smoke_release_availability.py")

        self.assertLess(gate, publish)
        self.assertLess(publish, smoke)
        self.assertIn("github.repository == 'tony9402/algorithm-local-judge'", workflow)
        self.assertIn("--require-manifest-sidecars", workflow)

    def test_release_matrix_builds_and_signs_supported_standalone_assets(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        parsed = yaml.load(workflow, Loader=yaml.BaseLoader)

        self.assertIsInstance(parsed, dict)
        verify_steps = parsed["jobs"]["verify"]["steps"]
        e2e_step = next(
            step for step in verify_steps if "unittest discover tests/e2e" in step.get("run", "")
        )
        self.assertEqual(e2e_step["env"]["ALJ_TOOL_COMPILE_TIMEOUT_MIN_MS"], "30000")
        for runner in ("ubuntu-latest", "macos-15", "macos-15-intel", "windows-latest"):
            self.assertIn(runner, workflow)
        for platform in ("macos-arm64", "macos-amd64", "linux-amd64", "windows-amd64"):
            self.assertIn(f"--required-platform {platform}", workflow)
        self.assertIn("dist/standalone/*.tar.gz", workflow)
        self.assertIn("for artifact in release-assets/*.tar.gz", workflow)
        self.assertIn("cosign sign-blob", workflow)
        self.assertIn("cosign sign --yes", workflow)
        self.assertIn("runner: ubuntu-24.04-arm", workflow)
        self.assertNotIn("docker/setup-qemu-action", workflow)
        for unsupported_step in (
            "scripts/build_rpm.py",
            "scripts/build_windows_installer.py",
            "scripts/build_winget_manifest.py",
            "scripts/build_macos_pkg.py",
            "scripts/build_apt_repository.py",
            "build_native_signing_plan.py",
            "APPLE_SIGNING_CERTIFICATE_P12",
            "APT_GPG_PRIVATE_KEY_BASE64",
        ):
            self.assertNotIn(unsupported_step, workflow)


if __name__ == "__main__":
    unittest.main()
