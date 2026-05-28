from __future__ import annotations

import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.paths import problem_source_root, rel
from judge.core.problem_install_policy import SOURCE_INSTALL_TRUST_WARNING
from judge.core.remote_archive import find_source_package_root, safe_extract_zip
from judge.utils.fs import write_json

SAFE_SOURCE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9_-]+")
DEFAULT_SOURCE_REF = "default"


def safe_source_component(value: str | None, fallback: str) -> str:
    """Return a filesystem-safe path component for installed source packages."""
    component = SAFE_SOURCE_COMPONENT_RE.sub("_", value or fallback).strip("_")
    return component or fallback


def reject_symlinks(path: Path) -> None:
    """Reject symlinks before copying source packages into the install area."""
    for item in path.rglob("*"):
        if item.is_symlink():
            raise JudgeError(f"refusing to install source package with symlink: {item}")


def source_problem_count(package_root: Path) -> int:
    """Return the number of problems in one source package root."""
    return len(list((package_root / "problems").glob("*/problem.json")))


def copy_testlib_if_needed(package_root: Path, target: Path) -> None:
    """Copy testlib.h into locations expected by source problem tools."""
    root_testlib = package_root / "testlib.h"
    problems_testlib = package_root / "problems" / "testlib.h"
    if root_testlib.exists() and root_testlib.is_file():
        shutil.copy2(root_testlib, target / "testlib.h")
        target_problem_testlib = target / "problems" / "testlib.h"
        if not target_problem_testlib.exists():
            shutil.copy2(root_testlib, target_problem_testlib)
    elif problems_testlib.exists() and problems_testlib.is_file():
        shutil.copy2(problems_testlib, target / "problems" / "testlib.h")


def install_problem_source_package(
    package_root: Path,
    *,
    repository: str | None = None,
    ref: str | None = None,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """Install a source problem package that contains a problems directory."""
    package_root = package_root.resolve()
    problems_dir = package_root / "problems"
    if not problems_dir.is_dir():
        raise JudgeError(f"source package has no problems directory: {package_root}")
    reject_symlinks(package_root)
    problem_count = source_problem_count(package_root)
    if problem_count == 0:
        raise JudgeError("source package has no problems/*/problem.json entries")

    repo_slug = safe_source_component(
        (repository or package_root.name).replace("/", "--"),
        "local",
    )
    ref_slug = safe_source_component(ref or DEFAULT_SOURCE_REF, DEFAULT_SOURCE_REF)
    target = problem_source_root() / repo_slug / ref_slug
    backup = None
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="alj-source-install-") as tmp:
        staged = Path(tmp) / "package"
        staged.mkdir(parents=True)
        shutil.copytree(problems_dir, staged / "problems")
        copy_testlib_if_needed(package_root, staged)
        write_json(
            staged / "source.json",
            {
                "schemaVersion": 1,
                "repository": repository,
                "ref": ref,
                "commitSha": commit_sha,
                "problemCount": problem_count,
                "installedAt": datetime.now(UTC)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
            },
        )
        if target.exists():
            backup = target.with_name(target.name + ".old")
            if backup.exists():
                shutil.rmtree(backup)
            target.rename(backup)
        shutil.copytree(staged, target)
        if backup is not None:
            shutil.rmtree(backup)
    return {
        "installedPath": str(target),
        "label": rel(target),
        "installType": "source",
        "repository": repository,
        "ref": ref,
        "commitSha": commit_sha,
        "problemCount": problem_count,
        "trustWarning": SOURCE_INSTALL_TRUST_WARNING,
    }


def install_problem_source_archive(
    archive_path: Path,
    *,
    repository: str | None = None,
    ref: str | None = None,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """Install a source problem package from a GitHub zip archive."""
    with tempfile.TemporaryDirectory(prefix="alj-source-extract-") as tmp:
        extracted_dir = Path(tmp)
        safe_extract_zip(archive_path, extracted_dir)
        package_root = find_source_package_root(extracted_dir)
        return install_problem_source_package(
            package_root,
            repository=repository,
            ref=ref,
            commit_sha=commit_sha,
        )
