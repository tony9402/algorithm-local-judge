from __future__ import annotations

import json
import os
import re
import ssl
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import certifi

from judge.core import security_limits
from judge.core.errors import JudgeError
from judge.core.paths import current_platform_id
from judge.utils.limited_io import copy_limited, ensure_content_length_limit

DEFAULT_OFFICIAL_PACK_REPOSITORY = "tony9402/algorithm-package"
ENV_CA_BUNDLE = "ALJ_CA_BUNDLE"
GITHUB_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_SSH_RE = re.compile(r"^git@github\.com:([^/]+)/(.+)$")


def normalize_repository_name(owner: str, repo: str) -> str:
    """Return a normalized GitHub `owner/name` repository string."""
    repo = repo.removesuffix(".git")
    candidate = f"{owner}/{repo}"
    if not GITHUB_REPOSITORY_RE.fullmatch(candidate):
        raise JudgeError("GitHub repository must look like owner/name")
    return candidate


def github_repository_from_source(source: str) -> str | None:
    """Parse GitHub repository information from owner/name, HTTPS, or SSH forms."""
    source = source.strip()
    if GITHUB_REPOSITORY_RE.fullmatch(source):
        owner, repo = source.split("/", 1)
        return normalize_repository_name(owner, repo)

    ssh_match = GITHUB_SSH_RE.fullmatch(source)
    if ssh_match:
        return normalize_repository_name(ssh_match.group(1), ssh_match.group(2))

    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower() in {
        "github.com",
        "www.github.com",
    }:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2:
            return normalize_repository_name(parts[0], parts[1])
    return None


def official_pack_repository(repository: str | None = None) -> str:
    """Return the configured official problem pack repository."""
    raw_repository = (
        repository
        or os.environ.get("ALJ_OFFICIAL_PACK_REPOSITORY")
        or DEFAULT_OFFICIAL_PACK_REPOSITORY
    )
    parsed = github_repository_from_source(raw_repository)
    if parsed is None:
        raise JudgeError("official repository must look like owner/name or a GitHub URL")
    return parsed


def ca_bundle_path() -> str:
    """Return the CA bundle path used for HTTPS downloads."""
    return os.environ.get(ENV_CA_BUNDLE) or certifi.where()


def https_ssl_context() -> ssl.SSLContext:
    """Build a verifying SSL context for GitHub and release asset downloads."""
    return ssl.create_default_context(cafile=ca_bundle_path())


def certificate_verification_failed(exc: BaseException) -> bool:
    """Return whether an exception represents a TLS certificate verification failure."""
    reason = getattr(exc, "reason", exc)
    return (
        isinstance(reason, ssl.SSLCertVerificationError)
        or isinstance(exc, ssl.SSLCertVerificationError)
        or "CERTIFICATE_VERIFY_FAILED" in str(reason)
        or "certificate verify failed" in str(reason).lower()
    )


def certificate_failure_message(prefix: str) -> str:
    """Return a user-facing certificate failure message."""
    return (
        f"{prefix}: SSL certificate verification failed. "
        "The judge uses HTTPS download, not git. Update your system certificates "
        f"or set {ENV_CA_BUNDLE}=/path/to/ca.pem."
    )


def github_json(url: str) -> dict[str, Any]:
    """Fetch a GitHub JSON document using the standard library."""
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "algorithm-local-judge",
        },
    )
    try:
        with urlopen(request, timeout=20, context=https_ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise JudgeError(f"GitHub request failed: HTTP {exc.code}") from exc
    except URLError as exc:
        if certificate_verification_failed(exc):
            raise JudgeError(certificate_failure_message("GitHub request failed")) from exc
        raise JudgeError(f"GitHub request failed: {exc.reason}") from exc


def github_default_branch(repository: str) -> str:
    """Return the default branch for a GitHub repository."""
    data = github_json(f"https://api.github.com/repos/{repository}")
    default_branch = data.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        raise JudgeError(f"GitHub repository has no default branch: {repository}")
    return default_branch


def github_commit_sha(repository: str, ref: str) -> str | None:
    """Return a commit SHA for a GitHub ref when GitHub exposes it."""
    try:
        data = github_json(f"https://api.github.com/repos/{repository}/commits/{ref}")
    except JudgeError:
        return None
    sha = data.get("sha")
    return sha if isinstance(sha, str) else None


def select_pack_asset(assets: list[dict[str, Any]], asset_name: str | None) -> dict[str, Any]:
    """Select a .aljpack release asset, preferring the current platform."""
    candidates = [
        asset
        for asset in assets
        if isinstance(asset.get("name"), str) and asset["name"].endswith(".aljpack")
    ]
    if asset_name:
        for asset in candidates:
            if asset["name"] == asset_name:
                return asset
        raise JudgeError(f"problem pack asset not found: {asset_name}")
    if not candidates:
        raise JudgeError("GitHub release has no .aljpack assets")
    platform_id = current_platform_id()
    for asset in candidates:
        if platform_id in asset["name"]:
            return asset
    return candidates[0]


def select_checksum_asset(
    assets: list[dict[str, Any]], pack_asset: dict[str, Any]
) -> dict[str, Any]:
    """Select the checksum asset associated with a release pack asset."""
    asset_name = pack_asset.get("name")
    if not isinstance(asset_name, str) or not asset_name.endswith(".aljpack"):
        raise JudgeError("problem pack asset has no valid name")
    expected_names = {
        f"{asset_name}.sha256",
        f"{asset_name.removesuffix('.aljpack')}.sha256",
    }
    for asset in assets:
        name = asset.get("name")
        if isinstance(name, str) and name in expected_names:
            return asset
    for asset in assets:
        if asset.get("name") == "checksums.txt":
            return asset
    raise JudgeError(f"GitHub release has no checksum asset for {asset_name}")


def download_asset(
    url: str,
    target: Path,
    *,
    limit_bytes: int = security_limits.MAX_REMOTE_DOWNLOAD_BYTES,
) -> None:
    """Download one release asset to a local file."""
    request = Request(url, headers={"User-Agent": "algorithm-local-judge"})
    try:
        with urlopen(request, timeout=60, context=https_ssl_context()) as response:
            ensure_content_length_limit(response.headers, limit_bytes, "remote download")
            copy_limited(
                response,
                target,
                limit_bytes=limit_bytes,
                label="remote download",
            )
    except HTTPError as exc:
        raise JudgeError(f"problem pack download failed: HTTP {exc.code}") from exc
    except URLError as exc:
        if certificate_verification_failed(exc):
            raise JudgeError(certificate_failure_message("problem pack download failed")) from exc
        raise JudgeError(f"problem pack download failed: {exc.reason}") from exc
