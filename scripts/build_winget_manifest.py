"""Generate local WinGet Community Repository manifests for an already-built MSI."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

import yaml

from judge import __version__

try:
    from scripts.build_windows_installer import SUPPORTED_PLATFORM, UPGRADE_CODE, msi_version
except ModuleNotFoundError:  # Direct `python scripts/build_winget_manifest.py` execution.
    from build_windows_installer import SUPPORTED_PLATFORM, UPGRADE_CODE, msi_version

MANIFEST_VERSION = "1.9.0"
PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


def validate_winget_platform(platform_id: str) -> None:
    if platform_id != SUPPORTED_PLATFORM:
        raise ValueError(f"unsupported WinGet platform: {platform_id}")


def sha256(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"MSI not found: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def manifest_payloads(
    msi_path: Path,
    package_id: str,
    version: str,
    installer_url: str,
    platform_id: str = SUPPORTED_PLATFORM,
) -> dict[str, dict]:
    validate_winget_platform(platform_id)
    msi_version(version)
    if not installer_url.startswith("https://") or msi_path.name not in installer_url:
        raise ValueError("WinGet installer URL must be HTTPS and end with the MSI filename")
    if not PACKAGE_ID_RE.fullmatch(package_id):
        raise ValueError("WinGet package identifier must include publisher and product")
    common = {"PackageIdentifier": package_id, "PackageVersion": version}
    return {
        "version": {
            **common,
            "DefaultLocale": "en-US",
            "ManifestType": "version",
            "ManifestVersion": MANIFEST_VERSION,
        },
        "installer": {
            **common,
            "InstallerType": "wix",
            "Scope": "machine",
            "MinimumOSVersion": "10.0.0.0",
            "UpgradeBehavior": "install",
            "Commands": ["judge", "problem-studio"],
            "Installers": [
                {
                    "Architecture": "x64",
                    "InstallerUrl": installer_url,
                    "InstallerSha256": sha256(msi_path),
                    "AppsAndFeaturesEntries": [{"UpgradeCode": UPGRADE_CODE}],
                }
            ],
            "ManifestType": "installer",
            "ManifestVersion": MANIFEST_VERSION,
        },
        "locale": {
            **common,
            "PackageLocale": "en-US",
            "Publisher": "Algorithm Local Judge maintainers",
            "PackageName": "Algorithm Local Judge",
            "License": "MIT",
            "ShortDescription": "Local web judge and problem authoring studio",
            "ManifestType": "defaultLocale",
            "ManifestVersion": MANIFEST_VERSION,
        },
    }


def write_manifests(payloads: dict[str, dict], output_dir: Path, package_id: str) -> list[Path]:
    version = str(payloads["version"]["PackageVersion"])
    publisher, *product_parts = package_id.split(".")
    output_dir = output_dir / publisher[0].lower() / publisher / ".".join(product_parts) / version
    output_dir.mkdir(parents=True, exist_ok=True)
    names = {
        "version": f"{package_id}.yaml",
        "installer": f"{package_id}.installer.yaml",
        "locale": f"{package_id}.locale.en-US.yaml",
    }
    outputs = []
    for kind, payload in payloads.items():
        output = output_dir / names[kind]
        output.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        outputs.append(output)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--msi", type=Path, required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--installer-url", required=True)
    parser.add_argument("--platform", default=SUPPORTED_PLATFORM)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payloads = manifest_payloads(
            args.msi,
            args.package_id,
            args.version,
            args.installer_url,
            args.platform,
        )
        outputs = write_manifests(payloads, args.output_dir, args.package_id)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"error: {exc}")
        return 1
    for output in outputs:
        print(f"Built WinGet manifest: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
