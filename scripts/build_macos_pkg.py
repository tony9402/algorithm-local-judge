"""Build a macOS PKG and require native signing/notarization for stable artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from alj_core.errors import JudgeError
from alj_core.pack_archive import safe_extract_tar
from judge import __version__

PACKAGE_NAME = "algorithm-local-judge"
PACKAGE_IDENTIFIER = "io.github.tony9402.algorithm-local-judge"
SUPPORTED_PLATFORMS = {"macos-arm64", "macos-amd64"}


@dataclass(frozen=True)
class SigningConfiguration:
    application_identity: str
    installer_identity: str
    notary_profile: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ValueError(f"{name} is required to build the macOS installer")
    return path


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"command failed ({command[0]}): {detail}")
    return result


def signing_configuration(environ: dict[str, str] | None = None) -> SigningConfiguration:
    environment = environ if environ is not None else os.environ
    values = {
        "APPLE_DEVELOPER_ID_APPLICATION": environment.get(
            "APPLE_DEVELOPER_ID_APPLICATION", ""
        ).strip(),
        "APPLE_DEVELOPER_ID_INSTALLER": environment.get(
            "APPLE_DEVELOPER_ID_INSTALLER", ""
        ).strip(),
        "APPLE_NOTARY_PROFILE": environment.get("APPLE_NOTARY_PROFILE", "").strip(),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"stable macOS signing credentials are missing: {', '.join(missing)}")
    return SigningConfiguration(
        application_identity=values["APPLE_DEVELOPER_ID_APPLICATION"],
        installer_identity=values["APPLE_DEVELOPER_ID_INSTALLER"],
        notary_profile=values["APPLE_NOTARY_PROFILE"],
    )


def stage_payload(standalone_archive: Path, stage: Path) -> Path:
    extraction = stage.parent / "standalone"
    extraction.mkdir(parents=True, exist_ok=True)
    try:
        safe_extract_tar(standalone_archive, extraction)
    except JudgeError as exc:
        raise ValueError(f"unsafe standalone archive: {exc}") from exc
    standalone = extraction / PACKAGE_NAME
    launchers = [standalone / "bin" / name for name in ("judge", "problem-studio")]
    for launcher in launchers:
        if not launcher.is_file() or not os.access(launcher, os.X_OK):
            raise ValueError(f"standalone archive has no executable: {launcher}")

    application = stage / "opt" / PACKAGE_NAME
    application.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(standalone, application, symlinks=True)
    binary_dir = stage / "usr" / "local" / "bin"
    binary_dir.mkdir(parents=True, exist_ok=True)
    for name in ("judge", "problem-studio"):
        (binary_dir / name).symlink_to(f"/opt/{PACKAGE_NAME}/bin/{name}")
    return application


def discover_mach_o_files(application: Path) -> list[Path]:
    file_tool = require_tool("file")
    mach_o_files = []
    for path in application.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        result = run_checked([file_tool, "--brief", str(path)])
        if "Mach-O" in result.stdout:
            mach_o_files.append(path)
    required = {application / "bin" / name for name in ("judge", "problem-studio")}
    if not required.issubset(mach_o_files):
        missing = ", ".join(path.name for path in sorted(required - set(mach_o_files)))
        raise ValueError(f"macOS launcher is not a Mach-O executable: {missing}")
    return sorted(
        mach_o_files,
        key=lambda path: (-len(path.relative_to(application).parts), path.as_posix()),
    )


def sign_application(application: Path, configuration: SigningConfiguration) -> None:
    codesign = require_tool("codesign")
    for binary in discover_mach_o_files(application):
        run_checked(
            [
                codesign,
                "--force",
                "--options",
                "runtime",
                "--timestamp",
                "--sign",
                configuration.application_identity,
                str(binary),
            ]
        )
        run_checked([codesign, "--verify", "--strict", "--verbose=2", str(binary)])


def notarize(package: Path, configuration: SigningConfiguration) -> dict[str, str]:
    xcrun = require_tool("xcrun")
    submission = run_checked(
        [
            xcrun,
            "notarytool",
            "submit",
            str(package),
            "--keychain-profile",
            configuration.notary_profile,
            "--wait",
            "--output-format",
            "json",
        ]
    )
    try:
        payload = json.loads(submission.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("notarytool returned invalid JSON") from exc
    submission_id = payload.get("id")
    if payload.get("status") != "Accepted" or not isinstance(submission_id, str):
        raise ValueError(f"Apple notarization was not accepted: {payload.get('status')}")
    run_checked([xcrun, "stapler", "staple", str(package)])
    run_checked([xcrun, "stapler", "validate", str(package)])
    spctl = require_tool("spctl")
    run_checked([spctl, "--assess", "--type", "install", "--verbose=2", str(package)])
    return {"provider": "apple-notarytool", "submissionId": submission_id}


def build_pkg(
    standalone_archive: Path,
    output_dir: Path,
    version: str,
    platform: str,
    *,
    stable: bool,
    environ: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"unsupported macOS package platform: {platform}")
    pkgbuild = require_tool("pkgbuild")
    configuration = signing_configuration(environ) if stable else None
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{PACKAGE_NAME}-{version}-{platform}.pkg"
    evidence_path = output_dir / f"{output.name}.native-signing.json"
    with tempfile.TemporaryDirectory(prefix="alj-macos-pkg-") as tmp:
        stage = Path(tmp) / "root"
        application = stage_payload(standalone_archive.resolve(), stage)
        if configuration is not None:
            sign_application(application, configuration)
        command = [
            pkgbuild,
            "--root",
            str(stage),
            "--identifier",
            PACKAGE_IDENTIFIER,
            "--version",
            version,
            "--install-location",
            "/",
        ]
        if configuration is not None:
            command.extend(["--sign", configuration.installer_identity])
        command.append(str(output))
        run_checked(command)
    if not output.is_file():
        raise ValueError("pkgbuild did not produce the expected installer")

    attestation = None
    status = "unconfigured"
    if configuration is not None:
        pkgutil = require_tool("pkgutil")
        run_checked([pkgutil, "--check-signature", str(output)])
        attestation = notarize(output, configuration)
        status = "verified"
    evidence = {
        "schemaVersion": 1,
        "target": "macos",
        "type": "developer-id",
        "status": status,
        "artifact": {"name": output.name, "sha256": sha256(output)},
        "attestation": attestation,
    }
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output, evidence_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("dist/installers"))
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--platform", choices=sorted(SUPPORTED_PLATFORMS), required=True)
    parser.add_argument("--channel", choices=["candidate", "stable"], default="candidate")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output, evidence = build_pkg(
            args.archive,
            args.output_dir,
            args.version,
            args.platform,
            stable=args.channel == "stable",
        )
    except (OSError, ValueError, JudgeError) as exc:
        print(f"error: {exc}")
        return 1
    print(f"Built macOS installer: {output}")
    print(f"Built native signing evidence: {evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
