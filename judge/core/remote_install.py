"""원격 설치 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from judge.core.checksums import verify_sha256_text
from judge.core.errors import JudgeError
from judge.core.paths import cache_root
from judge.core.remote_archive import safe_download_name
from judge.core.remote_downloads import (
    install_downloaded_problem_pack,
)
from judge.core.remote_github import (
    download_asset,
    github_commit_sha,
    github_default_branch,
    github_json,
    official_pack_repository,
    select_checksum_asset,
    select_pack_asset,
)
from judge.core.remote_trust import ensure_trusted_repository
from judge.core.source_install import (
    DEFAULT_SOURCE_REF,
    install_problem_source_archive,
    safe_source_component,
)


def download_problem_pack_from_github(
    repository: str | None = None,
    asset_name: str | None = None,
    ref: str | None = None,
) -> dict[str, Any]:
    """다운로드 문제 문제팩 GitHub 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        repository (str | None): GitHub owner/name 또는 URL에서 정규화할 저장소 식별자입니다.
        asset_name (str | None): asset 이름를 사용자 표시와 내부 조회에 함께 사용하는 이름입니다.
        ref (str | None): GitHub API나 Git 명령에서 사용할 브랜치, 태그, 커밋 참조입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 다운로드 문제 문제팩 GitHub 데이터입니다.
    """
    repo = ensure_trusted_repository(official_pack_repository(repository))
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
            checksum_asset = select_checksum_asset(release.get("assets", []), asset)
            checksum_url = checksum_asset.get("browser_download_url")
            if not isinstance(checksum_url, str):
                raise JudgeError(
                    f"problem pack checksum has no download URL: {checksum_asset.get('name')}"
                )
            target_dir = cache_root() / "downloads" / "packs"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / safe_download_name(asset.get("name"), "problem-pack.aljpack")
            checksum_target = target_dir / safe_download_name(
                checksum_asset.get("name"),
                f"{target.name}.sha256",
            )
            download_asset(download_url, target)
            download_asset(checksum_url, checksum_target)
            checksum = verify_sha256_text(target, checksum_target.read_text(encoding="utf-8"))
            result = install_downloaded_problem_pack(target)
            result.update(
                {
                    "installType": "pack",
                    "repository": repo,
                    "assetName": asset.get("name"),
                    "downloadedPath": str(target),
                    "trustedRepository": True,
                    "checksumVerified": True,
                    "checksumSource": checksum_asset.get("name"),
                    "checksumSha256": checksum,
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


def direct_pack_checksum_url(source_url: str, checksum_url: str | None) -> str:
    if checksum_url:
        parsed = urlparse(checksum_url)
        if parsed.scheme not in {"http", "https"}:
            raise JudgeError("direct problem pack checksum URL must be HTTP(S)")
        return checksum_url
    return f"{source_url}.sha256"


def download_problem_pack_from_url(
    source_url: str,
    *,
    checksum: str | None = None,
    checksum_url: str | None = None,
) -> dict[str, Any]:
    """다운로드 문제 문제팩 URL 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        source_url (str): 다운로드 문제 문제팩 URL을 계산하거나 검증할 때 필요한 소스 URL 입력입니다.
        checksum (str | None): 다운로드 문제 문제팩 URL을 계산하거나 검증할 때 필요한 체크섬 입력입니다.
        checksum_url (str | None): 다운로드 문제 문제팩 URL을 계산하거나 검증할 때 필요한 체크섬 URL 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 다운로드 문제 문제팩 URL 데이터입니다.
    """
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.path.endswith(".aljpack"):
        raise JudgeError("direct problem pack URL must be an HTTP(S) .aljpack URL")
    if checksum and checksum_url:
        raise JudgeError("use either --checksum or --checksum-url, not both")
    target_dir = cache_root() / "downloads" / "packs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_download_name(Path(parsed.path).name, "problem-pack.aljpack")
    download_asset(source_url, target)
    checksum_source = "--checksum"
    checksum_text = checksum
    checksum_target: Path | None = None
    if checksum_text is None:
        resolved_checksum_url = direct_pack_checksum_url(source_url, checksum_url)
        checksum_source = resolved_checksum_url
        checksum_target = target.with_name(
            safe_download_name(
                Path(urlparse(resolved_checksum_url).path).name, f"{target.name}.sha256"
            )
        )
        try:
            download_asset(resolved_checksum_url, checksum_target)
        except JudgeError as exc:
            target.unlink(missing_ok=True)
            checksum_target.unlink(missing_ok=True)
            raise JudgeError(
                "direct problem pack URL requires --checksum, --checksum-url, "
                "or a reachable <url>.sha256 sidecar"
            ) from exc
        checksum_text = checksum_target.read_text(encoding="utf-8")
    try:
        checksum_sha256 = verify_sha256_text(target, checksum_text)
    except Exception:
        target.unlink(missing_ok=True)
        if checksum_target is not None:
            checksum_target.unlink(missing_ok=True)
        raise
    result = install_downloaded_problem_pack(target)
    result.update(
        {
            "sourceUrl": source_url,
            "downloadedPath": str(target),
            "checksumVerified": True,
            "checksumSource": checksum_source,
            "checksumSha256": checksum_sha256,
        }
    )
    return result


__all__ = [
    "DEFAULT_SOURCE_REF",
    "direct_pack_checksum_url",
    "download_asset",
    "download_problem_pack_from_github",
    "download_problem_pack_from_url",
    "github_commit_sha",
    "github_default_branch",
    "github_json",
    "install_problem_source_archive",
    "safe_source_component",
]
