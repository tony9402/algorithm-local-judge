from __future__ import annotations

import re
from pathlib import Path

from judge.core.errors import JudgeError
from judge.utils.hashing import sha256_file

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def checksum_sidecar_path(artifact_path: Path) -> Path:
    """Return the SHA-256 sidecar path for a release artifact."""
    return artifact_path.with_name(f"{artifact_path.name}.sha256")


def parse_sha256_checksum(text: str, artifact_name: str) -> str:
    """Return the expected SHA-256 digest for an artifact from checksum text."""
    fallback_hash: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        digest = parts[0]
        if not SHA256_RE.fullmatch(digest):
            raise JudgeError("invalid SHA-256 checksum format")
        if len(parts) == 1:
            fallback_hash = digest.lower()
            continue
        candidate_name = Path(parts[-1].lstrip("*")).name
        if candidate_name == artifact_name:
            return digest.lower()
    if fallback_hash:
        return fallback_hash
    raise JudgeError(f"checksum entry not found for {artifact_name}")


def write_sha256_sidecar(artifact_path: Path) -> Path:
    """Write the standard sidecar SHA-256 checksum for an artifact."""
    checksum_path = checksum_sidecar_path(artifact_path)
    checksum_path.write_text(
        f"{sha256_file(artifact_path)}  {artifact_path.name}\n",
        encoding="utf-8",
    )
    return checksum_path


def verify_sha256_text(artifact_path: Path, checksum_text: str) -> str:
    """Validate a file against checksum text and return the matched digest."""
    expected = parse_sha256_checksum(checksum_text, artifact_path.name)
    actual = sha256_file(artifact_path)
    if actual.lower() != expected.lower():
        raise JudgeError(
            f"checksum mismatch for {artifact_path.name}: expected {expected}, got {actual}"
        )
    return expected.lower()


def verify_sha256_sidecar(artifact_path: Path) -> str:
    """Validate a file against its standard sidecar checksum."""
    checksum_path = checksum_sidecar_path(artifact_path)
    if not checksum_path.exists():
        raise JudgeError(f"missing checksum sidecar: {checksum_path.name}")
    return verify_sha256_text(artifact_path, checksum_path.read_text(encoding="utf-8"))
