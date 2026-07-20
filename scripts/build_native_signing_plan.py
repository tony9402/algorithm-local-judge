"""Create a credential-free native signing readiness plan; never signs artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

TARGETS = {
    "macos": {
        "type": "developer-id",
        "credentials": [
            "APPLE_DEVELOPER_ID_APPLICATION",
            "APPLE_DEVELOPER_ID_INSTALLER",
            "APPLE_NOTARY_PROFILE",
        ],
        "tools": ["codesign", "xcrun"],
    },
    "windows": {
        "type": "authenticode",
        "credentials": ["WINDOWS_SIGN_CERTIFICATE", "WINDOWS_SIGN_PASSWORD"],
        "tools": ["signtool"],
    },
    "apt": {
        "type": "apt-gpg",
        "credentials": ["ALJ_APT_GPG_KEY_ID"],
        "tools": ["gpg"],
    },
    "rpm": {
        "type": "rpm-gpg",
        "credentials": ["ALJ_RPM_GPG_KEY_ID"],
        "tools": ["gpg", "rpmsign"],
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_evidence(directory: Path | None) -> dict[str, dict[str, dict[str, object]]]:
    artifacts: dict[str, dict[str, dict[str, object]]] = {}
    if directory is None:
        return artifacts
    for path in sorted(directory.glob("*.native-signing.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"invalid native signing evidence {path.name}: {exc}") from exc
        target = payload.get("target")
        artifact = payload.get("artifact")
        if (
            payload.get("schemaVersion") != 1
            or target not in TARGETS
            or payload.get("type") != TARGETS[target]["type"]
            or payload.get("status") != "verified"
            or not isinstance(payload.get("attestation"), dict)
            or not isinstance(artifact, dict)
        ):
            continue
        name = artifact.get("name")
        expected = artifact.get("sha256")
        if not isinstance(name, str) or Path(name).name != name or not isinstance(expected, str):
            raise ValueError(f"native signing evidence has an unsafe artifact: {path.name}")
        signed_artifact = directory / name
        if not signed_artifact.is_file() or sha256(signed_artifact) != expected:
            raise ValueError(f"native signing evidence artifact hash mismatch: {name}")
        artifacts.setdefault(target, {})[name] = {
            "type": payload["type"],
            "status": "verified",
            "attestation": json.dumps(
                payload["attestation"], sort_keys=True, separators=(",", ":")
            ),
        }
    return artifacts


def signing_plan(
    environ: dict[str, str] | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, object]:
    environment = environ if environ is not None else os.environ
    evidence = load_evidence(evidence_dir)
    targets = {}
    for name, contract in TARGETS.items():
        missing_credentials = [key for key in contract["credentials"] if not environment.get(key)]
        missing_tools = [tool for tool in contract["tools"] if shutil.which(tool) is None]
        targets[name] = {
            "type": contract["type"],
            "status": "ready" if not missing_credentials and not missing_tools else "unconfigured",
            "missingCredentials": missing_credentials,
            "missingTools": missing_tools,
            "attestation": None,
            "artifacts": evidence.get(name, {}),
        }
    return {"schemaVersion": 1, "targets": targets}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        plan = signing_plan(evidence_dir=args.evidence_dir)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.require_ready:
        missing = [name for name, value in plan["targets"].items() if value["status"] != "ready"]
        if missing:
            print(f"error: native signing is not ready: {', '.join(missing)}")
            return 1
    print(f"Built native signing plan: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
