"""Cosign bundles used to sign and verify distributable problem packs."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError

ENV_COSIGN = "ALJ_COSIGN"
ENV_SIGNATURE_IDENTITY = "ALJ_PACK_SIGNATURE_IDENTITY"
ENV_SIGNATURE_ISSUER = "ALJ_PACK_SIGNATURE_ISSUER"
ENV_SIGNATURE_PUBLIC_KEY = "ALJ_PACK_SIGNATURE_PUBLIC_KEY"
DEFAULT_GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
COSIGN_TIMEOUT_SECONDS = 60


def default_bundle_path(archive_path: Path) -> Path:
    return archive_path.with_name(f"{archive_path.name}.sigstore.json")


def cosign_path() -> str:
    configured = os.environ.get(ENV_COSIGN)
    resolved = shutil.which(configured or "cosign")
    if resolved:
        return resolved
    raise JudgeError(
        "Cosign is required to verify official artifact signatures. "
        "Install it with `brew install cosign` on macOS/Linuxbrew or follow "
        "https://docs.sigstore.dev/cosign/system_config/installation/ on Linux. "
        f"Set {ENV_COSIGN}=/path/to/cosign when it is not on PATH."
    )


def github_workflow_identity_pattern(repository: str) -> str:
    escaped = re.escape(repository)
    return rf"^https://github\.com/{escaped}/\.github/workflows/[^@]+@refs/tags/.+$"


def _run_cosign(command: list[str], action: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=COSIGN_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise JudgeError(f"Cosign {action} timed out after {COSIGN_TIMEOUT_SECONDS}s") from exc
    except OSError as exc:
        raise JudgeError(f"Cosign {action} could not start: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if len(detail) > 2000:
            detail = f"{detail[:2000]}..."
        raise JudgeError(f"Cosign {action} failed: {detail or 'unknown error'}")
    return result


def verify_pack_signature(
    archive_path: Path,
    bundle_path: Path,
    repository: str,
) -> dict[str, Any]:
    """Verify a pack blob against a Sigstore bundle and an explicit publisher policy."""
    archive_path = archive_path.resolve()
    bundle_path = bundle_path.resolve()
    if not archive_path.is_file():
        raise JudgeError(f"problem pack not found: {archive_path}")
    if not bundle_path.is_file():
        raise JudgeError(f"problem pack signature bundle not found: {bundle_path}")

    return verify_sigstore_bundle(archive_path, bundle_path, repository)


def verify_sigstore_bundle(
    blob_path: Path,
    bundle_path: Path,
    repository: str,
) -> dict[str, Any]:
    """Verify any release blob against a Sigstore bundle and publisher policy."""
    blob_path = blob_path.resolve()
    bundle_path = bundle_path.resolve()
    if not blob_path.is_file():
        raise JudgeError(f"signed blob not found: {blob_path}")
    if not bundle_path.is_file():
        raise JudgeError(f"signature bundle not found: {bundle_path}")
    command = [
        cosign_path(),
        "verify-blob",
        str(blob_path),
        "--bundle",
        str(bundle_path),
    ]
    public_key = os.environ.get(ENV_SIGNATURE_PUBLIC_KEY)
    identity = os.environ.get(ENV_SIGNATURE_IDENTITY)
    issuer = os.environ.get(ENV_SIGNATURE_ISSUER) or DEFAULT_GITHUB_OIDC_ISSUER
    if public_key:
        command.extend(["--key", public_key])
        policy = {"publicKey": public_key, "identity": None, "issuer": None}
    else:
        if identity:
            command.extend(["--certificate-identity", identity])
            identity_policy = identity
        else:
            identity_policy = github_workflow_identity_pattern(repository)
            command.extend(["--certificate-identity-regexp", identity_policy])
        command.extend(["--certificate-oidc-issuer", issuer])
        policy = {"publicKey": None, "identity": identity_policy, "issuer": issuer}

    _run_cosign(command, "signature verification")
    return {
        "signatureVerified": True,
        "signatureBundle": str(bundle_path),
        "signatureIdentity": policy["identity"],
        "signatureIssuer": policy["issuer"],
        "signaturePublicKey": policy["publicKey"],
    }


def sign_pack(
    archive_path: Path,
    bundle_path: Path | None = None,
    key: str | None = None,
) -> Path:
    """Create the Sigstore bundle shipped next to a release problem pack."""
    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        raise JudgeError(f"problem pack not found: {archive_path}")
    if archive_path.suffix != ".aljpack":
        raise JudgeError("only .aljpack files can be signed")
    bundle_path = (bundle_path or default_bundle_path(archive_path)).resolve()
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        cosign_path(),
        "sign-blob",
        str(archive_path),
        "--bundle",
        str(bundle_path),
        "--yes",
    ]
    if key:
        command.extend(["--key", key])
    _run_cosign(command, "pack signing")
    if not bundle_path.is_file():
        raise JudgeError(f"Cosign did not create signature bundle: {bundle_path}")
    return bundle_path


__all__ = [
    "DEFAULT_GITHUB_OIDC_ISSUER",
    "ENV_COSIGN",
    "ENV_SIGNATURE_IDENTITY",
    "ENV_SIGNATURE_ISSUER",
    "ENV_SIGNATURE_PUBLIC_KEY",
    "cosign_path",
    "default_bundle_path",
    "github_workflow_identity_pattern",
    "sign_pack",
    "verify_sigstore_bundle",
    "verify_pack_signature",
]
