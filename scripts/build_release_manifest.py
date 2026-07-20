"""Build an immutable release manifest from already-produced local assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from judge import __version__
from judge.core.errors import JudgeError

APPLICATION_PATTERNS = (
    "algorithm-local-judge-*.tar.gz",
    "algorithm-local-judge_*.deb",
    "algorithm-local-judge-*.deb",
    "algorithm-local-judge-*.rpm",
    "alj-release-*.rpm",
    "algorithm-local-judge-*.pkg",
    "algorithm-local-judge-*.msi",
    "*.yaml",
    "algorithm-local-judge.rb",
    "install_local.sh",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise JudgeError(f"release sidecar is missing: {path.name}")
    return {"name": path.name, "sha256": sha256(path)}


def artifact_kind(path: Path) -> str:
    if path.name.endswith("-apt-repository.tar.gz"):
        return "apt-repository"
    if path.name.endswith(".tar.gz"):
        return "standalone"
    if path.suffix == ".deb":
        return "deb"
    if path.suffix == ".rpm":
        return "rpm"
    if path.suffix == ".pkg":
        return "pkg"
    if path.suffix == ".msi":
        return "msi"
    if path.suffix == ".yaml":
        return "winget-manifest"
    if path.suffix == ".rb":
        return "homebrew"
    if path.name == "install_local.sh":
        return "installer-script"
    raise JudgeError(f"unsupported release artifact: {path.name}")


def artifact_platform(path: Path, kind: str) -> str:
    for platform in ("macos-arm64", "macos-amd64", "linux-amd64", "windows-amd64"):
        if platform in path.name:
            return platform
    return {
        "deb": "linux-amd64",
        "rpm": "linux-amd64",
        "pkg": "macos-universal",
        "msi": "windows-amd64",
        "winget-manifest": "windows-amd64",
        "homebrew": "macos-linux",
        "installer-script": "macos-linux",
        "apt-repository": "linux-amd64",
    }.get(kind, "unknown")


def load_signing_plan(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"targets": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise JudgeError(f"native signing plan is invalid: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise JudgeError("native signing plan has an unsupported schema")
    return payload


def native_signing(
    name: str,
    kind: str,
    platform: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    target = None
    if kind == "winget-manifest":
        target = None
    elif kind == "pkg":
        target = "macos"
    elif platform.startswith("windows") or kind == "msi":
        target = "windows"
    elif kind == "apt-repository":
        target = "apt"
    elif kind == "rpm":
        target = "rpm"
    if target is None:
        return {"type": "sigstore-only", "status": "verified", "attestation": None}
    contract = (plan.get("targets") or {}).get(target) or {}
    contract = (contract.get("artifacts") or {}).get(name) or contract
    return {
        "type": contract.get(
            "type",
            {
                "macos": "developer-id",
                "windows": "authenticode",
                "apt": "apt-gpg",
                "rpm": "rpm-gpg",
            }[target],
        ),
        "status": contract.get("status", "unconfigured"),
        "attestation": contract.get("attestation"),
    }


def discover_artifacts(asset_root: Path) -> list[Path]:
    found = {}
    for pattern in APPLICATION_PATTERNS:
        for path in asset_root.glob(pattern):
            if path.is_file():
                found[path.name] = path
    return [found[name] for name in sorted(found)]


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    asset_root = args.assets.resolve()
    plan = load_signing_plan(args.signing_plan)
    artifacts = []
    for path in discover_artifacts(asset_root):
        kind = artifact_kind(path)
        platform = artifact_platform(path, kind)
        artifacts.append(
            {
                "name": path.name,
                "kind": kind,
                "platform": platform,
                "sha256": sha256(path),
                "checksum": sidecar(path.with_name(f"{path.name}.sha256")),
                "signature": sidecar(path.with_name(f"{path.name}.sigstore.json")),
                "launchers": ["judge", "problem-studio"],
                "nativeSigning": native_signing(path.name, kind, platform, plan),
            }
        )
    if not artifacts:
        raise JudgeError(f"no application release artifacts found in {asset_root}")
    sbom_path = asset_root / "algorithm-local-judge.cdx.json"
    official_values = (
        args.official_pack_repository,
        args.official_pack_ref,
        args.official_pack_asset,
        args.official_pack_sha256,
        args.official_pack_signature,
    )
    official_configured = all(official_values)
    return {
        "schemaVersion": 1,
        "release": {
            "version": args.version,
            "tag": args.tag,
            "channel": args.channel,
            "sourceCommit": args.source_commit,
            "immutable": True,
        },
        "requiredPlatforms": sorted(set(args.required_platform)),
        "artifacts": artifacts,
        "sbom": {
            "name": sbom_path.name,
            "format": "CycloneDX",
            "sha256": sha256(sbom_path),
            "checksum": sidecar(sbom_path.with_name(f"{sbom_path.name}.sha256")),
            "signature": sidecar(sbom_path.with_name(f"{sbom_path.name}.sigstore.json")),
        },
        "officialPack": {
            "status": "configured" if official_configured else "unconfigured",
            "repository": args.official_pack_repository or None,
            "ref": args.official_pack_ref or None,
            "asset": args.official_pack_asset or None,
            "sha256": args.official_pack_sha256 or None,
            "signature": args.official_pack_signature or None,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--channel", choices=["candidate", "stable"], default="candidate")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--required-platform", action="append", default=[])
    parser.add_argument("--signing-plan", type=Path)
    parser.add_argument("--official-pack-repository", default="")
    parser.add_argument("--official-pack-ref", default="")
    parser.add_argument("--official-pack-asset", default="")
    parser.add_argument("--official-pack-sha256", default="")
    parser.add_argument("--official-pack-signature", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = build_manifest(args)
    except (JudgeError, OSError) as exc:
        print(f"error: {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Built release manifest: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
