from __future__ import annotations

from judge.core.problem_install import (
    install_local_problem_source,
    install_problem_pack,
    install_problem_source,
)
from judge.core.remote_archive import (
    find_source_package_root,
    safe_download_name,
    safe_extract_zip,
    safe_zip_member_path,
)
from judge.core.remote_github import (
    DEFAULT_OFFICIAL_PACK_REPOSITORY,
    GITHUB_REPOSITORY_RE,
    GITHUB_SSH_RE,
    download_asset,
    github_commit_sha,
    github_default_branch,
    github_json,
    github_repository_from_source,
    normalize_repository_name,
    official_pack_repository,
    select_checksum_asset,
    select_pack_asset,
)
from judge.core.remote_install import (
    download_problem_pack_from_github,
    download_problem_pack_from_url,
)
from judge.core.remote_trust import (
    add_user_trusted_repository,
    default_trusted_owner_patterns,
    ensure_trusted_repository,
    is_trusted_repository,
    load_user_trusted_repositories,
    normalize_trusted_repository,
    remove_user_trusted_repository,
)
from judge.core.source_install import (
    DEFAULT_SOURCE_REF,
    SAFE_SOURCE_COMPONENT_RE,
    copy_testlib_if_needed,
    install_problem_source_archive,
    install_problem_source_package,
    reject_symlinks,
    safe_source_component,
    source_problem_count,
)

__all__ = [
    "DEFAULT_OFFICIAL_PACK_REPOSITORY",
    "DEFAULT_SOURCE_REF",
    "GITHUB_REPOSITORY_RE",
    "GITHUB_SSH_RE",
    "SAFE_SOURCE_COMPONENT_RE",
    "copy_testlib_if_needed",
    "download_asset",
    "download_problem_pack_from_github",
    "download_problem_pack_from_url",
    "find_source_package_root",
    "github_commit_sha",
    "github_default_branch",
    "github_json",
    "github_repository_from_source",
    "install_local_problem_source",
    "install_problem_pack",
    "install_problem_source",
    "install_problem_source_archive",
    "install_problem_source_package",
    "normalize_repository_name",
    "normalize_trusted_repository",
    "official_pack_repository",
    "reject_symlinks",
    "safe_download_name",
    "safe_extract_zip",
    "safe_source_component",
    "safe_zip_member_path",
    "select_checksum_asset",
    "select_pack_asset",
    "source_problem_count",
    "add_user_trusted_repository",
    "default_trusted_owner_patterns",
    "ensure_trusted_repository",
    "is_trusted_repository",
    "load_user_trusted_repositories",
    "remove_user_trusted_repository",
]
