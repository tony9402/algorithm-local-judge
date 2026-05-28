from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from judge.core.errors import JudgeError
from judge.core.pack import install_pack
from judge.core.paths import rel
from judge.core.problem_install_policy import PACK_INSTALL_TRUST_WARNING
from judge.core.remote_github import github_repository_from_source, official_pack_repository
from judge.core.remote_install import (
    download_problem_pack_from_github,
    download_problem_pack_from_url,
)
from judge.core.source_install import (
    DEFAULT_SOURCE_REF,
    install_problem_source_archive,
    install_problem_source_package,
)


def install_problem_pack(archive_path: Path) -> dict[str, Any]:
    """Install a local problem pack archive and return display metadata."""
    target = install_pack(archive_path)
    return {
        "installedPath": str(target),
        "label": rel(target),
        "installType": "pack",
        "trustWarning": PACK_INSTALL_TRUST_WARNING,
    }


def install_local_problem_source(
    local_path: Path,
    *,
    ref: str | None = None,
) -> dict[str, Any]:
    """Install problems from a local pack, source archive, or source directory."""
    if local_path.is_file():
        if local_path.suffix == ".aljpack":
            result = install_problem_pack(local_path.resolve())
            result.update({"source": str(local_path)})
            return result
        if local_path.suffix == ".zip":
            result = install_problem_source_archive(
                local_path.resolve(),
                repository=str(local_path.resolve()),
                ref=ref or DEFAULT_SOURCE_REF,
            )
            result.update({"source": str(local_path)})
            return result
    if local_path.is_dir() and (local_path / "problems").is_dir():
        result = install_problem_source_package(
            local_path,
            repository=str(local_path.resolve()),
            ref=ref or DEFAULT_SOURCE_REF,
        )
        result.update({"source": str(local_path)})
        return result
    raise JudgeError(
        "local problem install source must be a .aljpack file, "
        ".zip source archive, or source package"
    )


def install_problem_source(
    source: str | None,
    asset_name: str | None = None,
    ref: str | None = None,
    checksum: str | None = None,
    checksum_url: str | None = None,
) -> dict[str, Any]:
    """Install problems from a local pack, GitHub repository, or direct pack URL."""
    source = source or official_pack_repository()
    local_path = Path(source).expanduser()
    parsed_source = urlparse(source)
    direct_pack_url = parsed_source.scheme in {"http", "https"} and parsed_source.path.endswith(
        ".aljpack"
    )
    if (checksum or checksum_url) and (local_path.exists() or not direct_pack_url):
        raise JudgeError("checksum options are only supported for direct HTTP(S) .aljpack URLs")
    if local_path.exists():
        return install_local_problem_source(local_path, ref=ref)

    if direct_pack_url:
        return download_problem_pack_from_url(source, checksum=checksum, checksum_url=checksum_url)

    repository = github_repository_from_source(source)
    if repository is None:
        raise JudgeError(
            "problem install source must be a .aljpack path, owner/name, "
            "GitHub repository URL, or direct .aljpack URL"
        )
    return download_problem_pack_from_github(repository, asset_name, ref)
