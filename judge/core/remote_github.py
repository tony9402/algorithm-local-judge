"""remote_github 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
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
    """normalize_repository_name 함수를 실행하고 결과를 반환합니다.
    
    Args:
        owner (str): `owner` 값입니다.
        repo (str): 저장소 경로 또는 식별자입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    repo = repo.removesuffix(".git")
    candidate = f"{owner}/{repo}"
    if not GITHUB_REPOSITORY_RE.fullmatch(candidate):
        raise JudgeError("GitHub repository must look like owner/name")
    return candidate


def github_repository_from_source(source: str) -> str | None:
    """github_repository_from_source 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (str): `source` 값입니다.
    
    Returns:
        str | None: 처리 결과를 반환합니다.
    """
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
    """official_pack_repository 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repository (str | None): `repository` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
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
    """ca_bundle_path 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    return os.environ.get(ENV_CA_BUNDLE) or certifi.where()


def https_ssl_context() -> ssl.SSLContext:
    """https_ssl_context 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        ssl.SSLContext: 처리 결과를 반환합니다.
    """
    return ssl.create_default_context(cafile=ca_bundle_path())


def certificate_verification_failed(exc: BaseException) -> bool:
    """certificate_verification_failed 함수를 실행하고 결과를 반환합니다.
    
    Args:
        exc (BaseException): `exc` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    reason = getattr(exc, "reason", exc)
    return (
        isinstance(reason, ssl.SSLCertVerificationError)
        or isinstance(exc, ssl.SSLCertVerificationError)
        or "CERTIFICATE_VERIFY_FAILED" in str(reason)
        or "certificate verify failed" in str(reason).lower()
    )


def certificate_failure_message(prefix: str) -> str:
    """certificate_failure_message 함수를 실행하고 결과를 반환합니다.
    
    Args:
        prefix (str): `prefix` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    return (
        f"{prefix}: SSL certificate verification failed. "
        "The judge uses HTTPS download, not git. Update your system certificates "
        f"or set {ENV_CA_BUNDLE}=/path/to/ca.pem."
    )


def github_json(url: str) -> dict[str, Any]:
    """github_json 함수를 실행하고 결과를 반환합니다.
    
    Args:
        url (str): `url` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
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
    """github_default_branch 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repository (str): `repository` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    data = github_json(f"https://api.github.com/repos/{repository}")
    default_branch = data.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        raise JudgeError(f"GitHub repository has no default branch: {repository}")
    return default_branch


def github_commit_sha(repository: str, ref: str) -> str | None:
    """github_commit_sha 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repository (str): `repository` 값입니다.
        ref (str): `ref` 값입니다.
    
    Returns:
        str | None: 처리 결과를 반환합니다.
    """
    try:
        data = github_json(f"https://api.github.com/repos/{repository}/commits/{ref}")
    except JudgeError:
        return None
    sha = data.get("sha")
    return sha if isinstance(sha, str) else None


def select_pack_asset(assets: list[dict[str, Any]], asset_name: str | None) -> dict[str, Any]:
    """select_pack_asset 함수를 실행하고 결과를 반환합니다.
    
    Args:
        assets (list[dict[str, Any]]): `assets` 값입니다.
        asset_name (str | None): `asset_name` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
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
    """select_checksum_asset 함수를 실행하고 결과를 반환합니다.
    
    Args:
        assets (list[dict[str, Any]]): `assets` 값입니다.
        pack_asset (dict[str, Any]): `pack_asset` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
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
    """download_asset 함수를 실행하고 결과를 반환합니다.
    
    Args:
        url (str): `url` 값입니다.
        target (Path): `target` 값입니다.
        limit_bytes (int): `limit_bytes` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
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
