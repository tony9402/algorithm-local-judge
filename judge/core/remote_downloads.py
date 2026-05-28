"""remote_downloads 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from judge.core.errors import JudgeError
from judge.core.pack import install_pack
from judge.core.paths import cache_root, rel
from judge.core.problem_install_policy import PACK_INSTALL_TRUST_WARNING
from judge.core.remote_archive import safe_download_name
from judge.core.remote_github import (
    download_asset,
    github_commit_sha,
    github_default_branch,
    github_json,
    official_pack_repository,
    select_pack_asset,
)
from judge.core.source_install import (
    DEFAULT_SOURCE_REF,
    install_problem_source_archive,
    safe_source_component,
)


def install_downloaded_problem_pack(target: Path) -> dict[str, Any]:
    """install_downloaded_problem_pack 함수를 실행하고 결과를 반환합니다.
    
    Args:
        target (Path): `target` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    installed = install_pack(target)
    return {
        "installedPath": str(installed),
        "label": rel(installed),
        "installType": "pack",
        "trustWarning": PACK_INSTALL_TRUST_WARNING,
    }


def download_problem_pack_from_github(
    repository: str | None = None,
    asset_name: str | None = None,
    ref: str | None = None,
) -> dict[str, Any]:
    """download_problem_pack_from_github 함수를 실행하고 결과를 반환합니다.
    
    Args:
        repository (str | None): `repository` 값입니다.
        asset_name (str | None): `asset_name` 값입니다.
        ref (str | None): `ref` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    repo = official_pack_repository(repository)
    if not ref:
        try:
            release = github_json(f"https://api.github.com/repos/{repo}/releases/latest")
            asset = select_pack_asset(release.get("assets", []), asset_name)
        except JudgeError:
            if asset_name:
                raise
        else:
            download_url = asset.get("browser_download_url")
            if not isinstance(download_url, str):
                raise JudgeError(f"problem pack asset has no download URL: {asset.get('name')}")
            target_dir = cache_root() / "downloads" / "packs"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / safe_download_name(asset.get("name"), "problem-pack.aljpack")
            download_asset(download_url, target)
            result = install_downloaded_problem_pack(target)
            result.update(
                {
                    "repository": repo,
                    "assetName": asset.get("name"),
                    "downloadedPath": str(target),
                }
            )
            return result

    source_ref = ref or github_default_branch(repo)
    commit_sha = github_commit_sha(repo, source_ref)
    target_dir = cache_root() / "downloads" / "sources"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_download_name(
        f"{safe_source_component(repo.replace('/', '--'), 'repository')}-"
        f"{safe_source_component(source_ref, DEFAULT_SOURCE_REF)}.zip",
        "problem-source.zip",
    )
    download_asset(f"https://api.github.com/repos/{repo}/zipball/{source_ref}", target)
    result = install_problem_source_archive(
        target,
        repository=repo,
        ref=source_ref,
        commit_sha=commit_sha,
    )
    result["downloadedPath"] = str(target)
    return result


def download_problem_pack_from_url(source_url: str) -> dict[str, Any]:
    """download_problem_pack_from_url 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source_url (str): `source_url` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.path.endswith(".aljpack"):
        raise JudgeError("direct problem pack URL must be an HTTP(S) .aljpack URL")
    target_dir = cache_root() / "downloads" / "packs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_download_name(Path(parsed.path).name, "problem-pack.aljpack")
    download_asset(source_url, target)
    result = install_downloaded_problem_pack(target)
    result.update({"sourceUrl": source_url, "downloadedPath": str(target)})
    return result
