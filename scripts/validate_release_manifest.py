"""Validate immutable release assets and fail closed before stable publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import yaml

from judge.core.errors import JudgeError
from judge.core.pack_signatures import verify_sigstore_bundle
from scripts.scan_release_artifact import scan_standalone_archive

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_LAUNCHERS = {"judge", "problem-studio"}
ARTIFACT_KINDS = {
    "standalone",
    "deb",
    "rpm",
    "pkg",
    "msi",
    "winget-manifest",
    "homebrew",
    "installer-script",
    "apt-repository",
}
NATIVE_SIGNING_TYPES = {
    "sigstore-only",
    "developer-id",
    "authenticode",
    "apt-gpg",
    "rpm-gpg",
}
VERIFY_RELEASE_SIGNATURES_ENV = "ALJ_VERIFY_RELEASE_SIGNATURES"
RELEASE_SIGNATURE_REPOSITORY_ENV = "ALJ_RELEASE_SIGNATURE_REPOSITORY"
DEFAULT_RELEASE_SIGNATURE_REPOSITORY = "tony9402/algorithm-local-judge"


def require_keys(value: object, required: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise JudgeError(f"release manifest {label} must be an object")
    keys = set(value)
    missing = sorted(required - keys)
    unknown = sorted(keys - required)
    if missing:
        raise JudgeError(f"release manifest {label} is missing: {', '.join(missing)}")
    if unknown:
        raise JudgeError(f"release manifest {label} has unknown fields: {', '.join(unknown)}")
    return value


def validate_schema_shape(payload: dict[str, Any]) -> None:
    require_keys(
        payload,
        {"schemaVersion", "release", "requiredPlatforms", "artifacts", "sbom", "officialPack"},
        "root",
    )
    release = require_keys(
        payload["release"],
        {"version", "tag", "channel", "sourceCommit", "immutable"},
        "release",
    )
    if release.get("channel") not in {"candidate", "stable"}:
        raise JudgeError("release manifest channel is invalid")
    if not isinstance(release.get("version"), str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+", release["version"]
    ):
        raise JudgeError("release manifest version is invalid")
    if not isinstance(payload["artifacts"], list):
        raise JudgeError("release manifest artifacts must be an array")
    if not isinstance(payload["requiredPlatforms"], list):
        raise JudgeError("release manifest requiredPlatforms must be an array")
    for index, artifact_value in enumerate(payload["artifacts"]):
        artifact = require_keys(
            artifact_value,
            {
                "name",
                "kind",
                "platform",
                "sha256",
                "checksum",
                "signature",
                "launchers",
                "nativeSigning",
            },
            f"artifacts[{index}]",
        )
        if artifact.get("kind") not in ARTIFACT_KINDS:
            raise JudgeError(f"release manifest artifact kind is invalid: {artifact.get('kind')}")
        require_keys(artifact["checksum"], {"name", "sha256"}, "artifact checksum")
        require_keys(artifact["signature"], {"name", "sha256"}, "artifact signature")
        native = require_keys(
            artifact["nativeSigning"],
            {"type", "status", "attestation"},
            "artifact nativeSigning",
        )
        if native.get("type") not in NATIVE_SIGNING_TYPES or native.get("status") not in {
            "unconfigured",
            "ready",
            "verified",
        }:
            raise JudgeError("release manifest native signing state is invalid")
    sbom = require_keys(
        payload["sbom"],
        {"name", "format", "sha256", "checksum", "signature"},
        "sbom",
    )
    require_keys(sbom["checksum"], {"name", "sha256"}, "SBOM checksum")
    require_keys(sbom["signature"], {"name", "sha256"}, "SBOM signature")
    official = require_keys(
        payload["officialPack"],
        {"status", "repository", "ref", "asset", "sha256", "signature"},
        "officialPack",
    )
    if official.get("status") not in {"configured", "unconfigured"}:
        raise JudgeError("release manifest officialPack status is invalid")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def safe_asset(root: Path, name: object) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise JudgeError(f"release manifest contains an unsafe asset name: {name}")
    return root / name


def require_hash(path: Path, expected: object, label: str) -> None:
    if not path.is_file():
        raise JudgeError(f"{label} is missing: {path.name}")
    if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
        raise JudgeError(f"{label} has an invalid SHA-256 value")
    if sha256(path) != expected:
        raise JudgeError(f"{label} hash mismatch: {path.name}")


def validate_sidecars(root: Path, target: Path, record: dict[str, Any]) -> None:
    checksum = record.get("checksum")
    signature = record.get("signature")
    if not isinstance(checksum, dict) or not isinstance(signature, dict):
        raise JudgeError(f"release asset sidecars are incomplete: {target.name}")
    checksum_path = safe_asset(root, checksum.get("name"))
    signature_path = safe_asset(root, signature.get("name"))
    require_hash(checksum_path, checksum.get("sha256"), "checksum sidecar")
    require_hash(signature_path, signature.get("sha256"), "signature sidecar")
    try:
        expected = checksum_path.read_text(encoding="utf-8").split()[0].lower()
    except (IndexError, OSError) as exc:
        raise JudgeError(f"checksum sidecar is invalid: {checksum_path.name}") from exc
    if expected != record.get("sha256"):
        raise JudgeError(f"checksum sidecar does not match manifest: {target.name}")
    try:
        signature_payload = json.loads(signature_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise JudgeError(f"signature bundle is invalid: {signature_path.name}") from exc
    if not isinstance(signature_payload, dict) or not {
        "mediaType",
        "verificationMaterial",
        "messageSignature",
    }.issubset(signature_payload):
        raise JudgeError(
            f"signature bundle has no Sigstore bundle structure: {signature_path.name}"
        )
    if os.environ.get(VERIFY_RELEASE_SIGNATURES_ENV) == "1":
        if not signature_payload.get("verificationMaterial") or not signature_payload.get(
            "messageSignature"
        ):
            raise JudgeError(f"signature bundle is empty: {signature_path.name}")
        repository = os.environ.get(
            RELEASE_SIGNATURE_REPOSITORY_ENV,
            DEFAULT_RELEASE_SIGNATURE_REPOSITORY,
        )
        verify_sigstore_bundle(target, signature_path, repository)


def validate_deb_launchers(path: Path) -> None:
    dpkg_deb = shutil.which("dpkg-deb")
    if dpkg_deb is None:
        raise JudgeError("dpkg-deb is required to validate Debian launcher contents")
    result = subprocess.run(
        [dpkg_deb, "--contents", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise JudgeError(f"could not inspect Debian artifact: {result.stderr.strip()}")
    for launcher in REQUIRED_LAUNCHERS:
        if f"usr/bin/{launcher}" not in result.stdout:
            raise JudgeError(f"Debian artifact is missing launcher: {launcher}")


def load_winget_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise JudgeError(f"WinGet manifest is invalid: {path.name}") from exc
    if not isinstance(payload, dict):
        raise JudgeError(f"WinGet manifest must be an object: {path.name}")
    required = {"PackageIdentifier", "PackageVersion", "ManifestType", "ManifestVersion"}
    if not required.issubset(payload):
        raise JudgeError(f"WinGet manifest is incomplete: {path.name}")
    return payload


def validate_winget_installer_payload(path: Path, payload: dict[str, Any]) -> None:
    if payload.get("InstallerType") != "wix" or payload.get("Scope") != "machine":
        raise JudgeError(f"WinGet installer must declare a machine-scoped WiX MSI: {path.name}")
    commands = payload.get("Commands")
    if not isinstance(commands, list) or set(commands) != REQUIRED_LAUNCHERS:
        raise JudgeError(f"WinGet installer must expose both commands: {path.name}")
    installers = payload.get("Installers")
    if not isinstance(installers, list) or len(installers) != 1:
        raise JudgeError(f"WinGet installer must contain exactly one installer: {path.name}")
    installer = installers[0]
    if not isinstance(installer, dict) or installer.get("Architecture") != "x64":
        raise JudgeError(f"WinGet installer must target x64: {path.name}")
    installer_url = installer.get("InstallerUrl")
    if not isinstance(installer_url, str) or urlparse(installer_url).scheme != "https":
        raise JudgeError(f"WinGet installer URL must use HTTPS: {path.name}")
    installer_hash = installer.get("InstallerSha256")
    if not isinstance(installer_hash, str) or not SHA256_RE.fullmatch(installer_hash.lower()):
        raise JudgeError(f"WinGet installer SHA-256 is invalid: {path.name}")


def validate_launchers(path: Path, artifact: dict[str, Any]) -> None:
    launchers = artifact.get("launchers")
    if not isinstance(launchers, list) or set(launchers) != REQUIRED_LAUNCHERS:
        raise JudgeError(f"artifact must declare both launchers: {path.name}")
    kind = artifact.get("kind")
    if kind == "standalone":
        scan_standalone_archive(path)
    elif kind == "deb":
        validate_deb_launchers(path)
    elif kind == "winget-manifest":
        payload = load_winget_manifest(path)
        if payload.get("ManifestType") == "installer":
            validate_winget_installer_payload(path, payload)
    elif kind in {"homebrew", "installer-script"}:
        text = path.read_text(encoding="utf-8")
        if "problem-studio" not in text or "judge" not in text:
            raise JudgeError(f"installer does not expose both launchers: {path.name}")


def validate_apt_repository(path: Path, *, require_signed: bool) -> None:
    try:
        with tarfile.open(path, "r:gz") as archive:
            names = set()
            for member in archive.getmembers():
                member_path = Path(member.name)
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or member.issym()
                    or member.islnk()
                ):
                    raise JudgeError(f"APT repository archive contains unsafe paths: {path.name}")
                names.add(member.name)
    except (OSError, tarfile.TarError) as exc:
        raise JudgeError(f"APT repository archive is invalid: {path.name}") from exc
    required = {
        "dists/stable/Release",
        "dists/stable/main/binary-amd64/Packages",
        "dists/stable/main/binary-amd64/Packages.gz",
    }
    if not required.issubset(names) or not any(
        name.startswith("pool/main/a/algorithm-local-judge/") and name.endswith(".deb")
        for name in names
    ):
        raise JudgeError(f"APT repository archive is incomplete: {path.name}")
    if require_signed and not {"dists/stable/InRelease", "dists/stable/Release.gpg"}.issubset(
        names
    ):
        raise JudgeError(f"stable APT repository metadata is unsigned: {path.name}")


def validate_winget_assets(root: Path, artifacts: list[dict[str, Any]]) -> None:
    records = [artifact for artifact in artifacts if artifact.get("kind") == "winget-manifest"]
    if not records:
        return
    payloads = [load_winget_manifest(safe_asset(root, record.get("name"))) for record in records]
    manifest_types = [payload.get("ManifestType") for payload in payloads]
    if sorted(manifest_types) != ["defaultLocale", "installer", "version"]:
        raise JudgeError(
            "WinGet release assets must contain version, installer, and locale manifests"
        )
    identities = {
        (payload.get("PackageIdentifier"), payload.get("PackageVersion")) for payload in payloads
    }
    if len(identities) != 1 or not all(
        isinstance(value, str) and value for value in next(iter(identities))
    ):
        raise JudgeError("WinGet release manifests do not share one package identity")
    installer_payload = next(
        payload for payload in payloads if payload.get("ManifestType") == "installer"
    )
    installer = installer_payload["Installers"][0]
    installer_name = Path(unquote(urlparse(installer["InstallerUrl"]).path)).name
    msi_records = [artifact for artifact in artifacts if artifact.get("kind") == "msi"]
    matching_msi = [artifact for artifact in msi_records if artifact.get("name") == installer_name]
    if len(matching_msi) != 1:
        raise JudgeError("WinGet installer URL does not reference the release MSI asset")
    if installer["InstallerSha256"].lower() != matching_msi[0].get("sha256"):
        raise JudgeError("WinGet installer SHA-256 does not match the release MSI asset")


def validate_stable_package_assets(
    artifacts: list[dict[str, Any]], required_platforms: list[Any]
) -> None:
    if "linux-amd64" in required_platforms:
        if not any(
            artifact.get("kind") == "deb"
            and str(artifact.get("name")).startswith("algorithm-local-judge_")
            and str(artifact.get("name")).endswith("_amd64.deb")
            for artifact in artifacts
        ):
            raise JudgeError("stable Linux release is missing the Debian package")
        rpm_names = {
            str(artifact.get("name")) for artifact in artifacts if artifact.get("kind") == "rpm"
        }
        if not any(name.startswith("algorithm-local-judge-") for name in rpm_names):
            raise JudgeError("stable Linux release is missing the application RPM")
        if not any(name.startswith("alj-release-") for name in rpm_names):
            raise JudgeError("stable Linux release is missing the repository bootstrap RPM")
        if not any(artifact.get("kind") == "apt-repository" for artifact in artifacts):
            raise JudgeError("stable Linux release is missing the signed APT repository")
        if not any(
            artifact.get("kind") == "deb"
            and str(artifact.get("name")).startswith("algorithm-local-judge-archive-keyring_")
            for artifact in artifacts
        ):
            raise JudgeError("stable Linux release is missing the APT bootstrap package")
    if "windows-amd64" in required_platforms:
        if not any(artifact.get("kind") == "msi" for artifact in artifacts):
            raise JudgeError("stable Windows release is missing the WiX MSI")
        if not any(artifact.get("kind") == "winget-manifest" for artifact in artifacts):
            raise JudgeError("stable Windows release is missing the WinGet manifests")
    for platform in ("macos-arm64", "macos-amd64"):
        if platform in required_platforms and not any(
            artifact.get("kind") == "pkg" and artifact.get("platform") == platform
            for artifact in artifacts
        ):
            raise JudgeError(f"stable macOS release is missing the {platform} PKG")


def validate_artifacts(
    root: Path,
    artifacts: object,
    required_platforms: object,
    *,
    stable: bool,
) -> None:
    if not isinstance(artifacts, list) or not artifacts:
        raise JudgeError("release manifest has no application artifacts")
    names = []
    standalone_platforms = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise JudgeError("release manifest artifact must be an object")
        path = safe_asset(root, artifact.get("name"))
        names.append(path.name)
        require_hash(path, artifact.get("sha256"), "release artifact")
        validate_sidecars(root, path, artifact)
        validate_launchers(path, artifact)
        if artifact.get("kind") == "apt-repository":
            validate_apt_repository(path, require_signed=stable)
        if artifact.get("kind") == "standalone":
            standalone_platforms.add(artifact.get("platform"))
        native = artifact.get("nativeSigning")
        if not isinstance(native, dict):
            raise JudgeError(f"native signing contract is missing: {path.name}")
        if stable and native.get("type") != "sigstore-only":
            attestation = native.get("attestation")
            if (
                native.get("status") != "verified"
                or not isinstance(attestation, str)
                or not attestation.strip()
            ):
                raise JudgeError(
                    f"stable release native signing is not verified for {path.name}: "
                    f"{native.get('type')}"
                )
    if len(names) != len(set(names)):
        raise JudgeError("release manifest contains duplicate artifact names")
    if not isinstance(required_platforms, list) or not required_platforms:
        raise JudgeError("release manifest requiredPlatforms must not be empty")
    missing = sorted(set(required_platforms) - standalone_platforms)
    if missing:
        raise JudgeError(f"release manifest is missing OS artifact(s): {', '.join(missing)}")
    validate_winget_assets(root, artifacts)
    if stable:
        validate_stable_package_assets(artifacts, required_platforms)


def validate_sbom(root: Path, record: object) -> None:
    if not isinstance(record, dict) or record.get("format") != "CycloneDX":
        raise JudgeError("release manifest requires a CycloneDX SBOM")
    path = safe_asset(root, record.get("name"))
    require_hash(path, record.get("sha256"), "SBOM")
    validate_sidecars(root, path, record)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise JudgeError(f"SBOM is invalid: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("bomFormat") != "CycloneDX":
        raise JudgeError("SBOM content is not CycloneDX")


def validate_official_pack(record: object, *, stable: bool) -> None:
    if not isinstance(record, dict):
        raise JudgeError("official pack reference is missing")
    if not stable:
        return
    if record.get("status") != "configured":
        raise JudgeError("stable release official pack reference is unconfigured")
    repository = record.get("repository")
    immutable_ref = record.get("ref")
    if (
        not isinstance(repository, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or not isinstance(immutable_ref, str)
        or not COMMIT_RE.fullmatch(immutable_ref)
    ):
        raise JudgeError("stable release official pack must use an immutable commit reference")
    if not record.get("asset") or not record.get("signature"):
        raise JudgeError("stable release official pack asset/signature reference is incomplete")
    if not isinstance(record.get("sha256"), str) or not SHA256_RE.fullmatch(record["sha256"]):
        raise JudgeError("stable release official pack SHA-256 is invalid")


def validate_manifest_sidecars(manifest_path: Path) -> None:
    root = manifest_path.parent
    checksum_path = root / f"{manifest_path.name}.sha256"
    signature_path = root / f"{manifest_path.name}.sigstore.json"
    if not checksum_path.is_file() or not signature_path.is_file():
        raise JudgeError("stable release manifest checksum/signature sidecars are missing")
    try:
        expected = checksum_path.read_text(encoding="utf-8").split()[0].lower()
        signature = json.loads(signature_path.read_text(encoding="utf-8"))
    except (IndexError, json.JSONDecodeError, OSError) as exc:
        raise JudgeError("stable release manifest sidecars are invalid") from exc
    if (
        expected != sha256(manifest_path)
        or not isinstance(signature, dict)
        or not {"mediaType", "verificationMaterial", "messageSignature"}.issubset(signature)
    ):
        raise JudgeError("stable release manifest sidecars do not verify")
    if os.environ.get(VERIFY_RELEASE_SIGNATURES_ENV) == "1":
        if not signature.get("verificationMaterial") or not signature.get("messageSignature"):
            raise JudgeError("stable release manifest signature bundle is empty")
        repository = os.environ.get(
            RELEASE_SIGNATURE_REPOSITORY_ENV,
            DEFAULT_RELEASE_SIGNATURE_REPOSITORY,
        )
        verify_sigstore_bundle(manifest_path, signature_path, repository)


def validate_release_manifest(
    manifest_path: Path,
    asset_root: Path,
    *,
    stable: bool = False,
    require_manifest_sidecars: bool = False,
) -> dict[str, Any]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise JudgeError(f"release manifest is invalid: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise JudgeError("release manifest has an unsupported schemaVersion")
    validate_schema_shape(payload)
    release = payload.get("release")
    if not isinstance(release, dict) or release.get("immutable") is not True:
        raise JudgeError("release manifest must be immutable")
    if release.get("tag") != f"v{release.get('version')}":
        raise JudgeError("release tag does not match release version")
    if stable:
        if release.get("channel") != "stable":
            raise JudgeError("stable publish requires a stable release manifest")
        if not isinstance(release.get("sourceCommit"), str) or not COMMIT_RE.fullmatch(
            release["sourceCommit"]
        ):
            raise JudgeError("stable release sourceCommit must be immutable")
    validate_artifacts(
        asset_root.resolve(),
        payload.get("artifacts"),
        payload.get("requiredPlatforms"),
        stable=stable,
    )
    validate_sbom(asset_root.resolve(), payload.get("sbom"))
    validate_official_pack(payload.get("officialPack"), stable=stable)
    if require_manifest_sidecars:
        validate_manifest_sidecars(manifest_path)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--stable", action="store_true")
    parser.add_argument("--require-manifest-sidecars", action="store_true")
    args = parser.parse_args()
    try:
        validate_release_manifest(
            args.manifest.resolve(),
            args.assets.resolve(),
            stable=args.stable,
            require_manifest_sidecars=args.require_manifest_sidecars,
        )
    except JudgeError as exc:
        print(f"error: {exc}")
        return 1
    print(f"OK: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
