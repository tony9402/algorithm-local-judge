from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from judge.core.errors import JudgeError
from judge.core.pack import install_pack
from judge.core.paths import cache_root, current_platform_id, rel

DEFAULT_OFFICIAL_PACK_REPOSITORY = "tony9402/algorithm-modules"
GITHUB_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_SSH_RE = re.compile(r"^git@github\.com:([^/]+)/(.+)$")


def safe_download_name(filename: str | None, fallback: str) -> str:
    """Return a basename-only filename for a downloaded artifact."""
    name = Path(filename or fallback).name
    if not name or name in {".", ".."}:
        raise JudgeError("invalid download filename")
    return name


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
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise JudgeError(f"GitHub request failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise JudgeError(f"GitHub request failed: {exc.reason}") from exc


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


def download_asset(url: str, target: Path) -> None:
    """Download one release asset to a local file."""
    request = Request(url, headers={"User-Agent": "algorithm-local-judge"})
    try:
        with urlopen(request, timeout=60) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output)
    except HTTPError as exc:
        raise JudgeError(f"problem pack download failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise JudgeError(f"problem pack download failed: {exc.reason}") from exc


def install_problem_pack(archive_path: Path) -> dict[str, Any]:
    """Install a local problem pack archive and return display metadata."""
    target = install_pack(archive_path)
    return {"installedPath": str(target), "label": rel(target)}


def download_problem_pack_from_github(
    repository: str | None = None,
    asset_name: str | None = None,
) -> dict[str, Any]:
    """Download and install a problem pack from a public GitHub release."""
    repo = official_pack_repository(repository)
    release = github_json(f"https://api.github.com/repos/{repo}/releases/latest")
    asset = select_pack_asset(release.get("assets", []), asset_name)
    download_url = asset.get("browser_download_url")
    if not isinstance(download_url, str):
        raise JudgeError(f"problem pack asset has no download URL: {asset.get('name')}")
    target_dir = cache_root() / "downloads" / "packs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_download_name(asset.get("name"), "problem-pack.aljpack")
    download_asset(download_url, target)
    result = install_problem_pack(target)
    result.update(
        {
            "repository": repo,
            "assetName": asset.get("name"),
            "downloadedPath": str(target),
        }
    )
    return result


def download_problem_pack_from_url(source_url: str) -> dict[str, Any]:
    """Download and install a problem pack from a direct HTTP(S) .aljpack URL."""
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.path.endswith(".aljpack"):
        raise JudgeError("direct problem pack URL must be an HTTP(S) .aljpack URL")
    target_dir = cache_root() / "downloads" / "packs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_download_name(Path(parsed.path).name, "problem-pack.aljpack")
    download_asset(source_url, target)
    result = install_problem_pack(target)
    result.update({"sourceUrl": source_url, "downloadedPath": str(target)})
    return result


def install_problem_source(source: str | None, asset_name: str | None = None) -> dict[str, Any]:
    """Install problems from a local pack, GitHub repository, or direct pack URL."""
    source = source or official_pack_repository()
    local_path = Path(source).expanduser()
    if local_path.exists():
        if local_path.is_file() and local_path.suffix == ".aljpack":
            result = install_problem_pack(local_path.resolve())
            result.update({"source": str(local_path)})
            return result
        raise JudgeError("local problem install source must be a .aljpack file")

    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"} and parsed.path.endswith(".aljpack"):
        return download_problem_pack_from_url(source)

    repository = github_repository_from_source(source)
    if repository is None:
        raise JudgeError(
            "problem install source must be a .aljpack path, owner/name, "
            "GitHub repository URL, or direct .aljpack URL"
        )
    return download_problem_pack_from_github(repository, asset_name)
