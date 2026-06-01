"""소스 설치 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.paths import problem_source_root, rel, repo_root
from judge.core.problem_install_policy import SOURCE_INSTALL_TRUST_WARNING
from judge.core.remote_archive import find_source_package_root, safe_extract_zip
from judge.utils.fs import write_json

SAFE_SOURCE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9_-]+")
DEFAULT_SOURCE_REF = "default"


def safe_source_component(value: str | None, fallback: str) -> str:
    component = SAFE_SOURCE_COMPONENT_RE.sub("_", value or fallback).strip("_")
    return component or fallback


def reject_symlinks(path: Path) -> None:
    for item in path.rglob("*"):
        if item.is_symlink():
            raise JudgeError(f"refusing to install source package with symlink: {item}")


def source_problem_count(package_root: Path) -> int:
    return len(list((package_root / "problems").glob("*/problem.json")))


def copy_testlib_if_needed(package_root: Path, target: Path) -> None:
    """소스 패키지나 애플리케이션에 포함된 testlib.h를 설치된 문제 루트에 배치합니다.

    Args:
        package_root (Path): 원격 또는 로컬에서 가져온 문제 소스 패키지의 루트 디렉터리입니다.
        target (Path): 설치된 source package를 staging하는 디렉터리입니다. 문제 도구의 상대 include
            경로가 동작하도록 testlib.h를 이 디렉터리와 `problems/` 아래에 복사합니다.
    """
    candidates = [
        package_root / "testlib.h",
        package_root / "problems" / "testlib.h",
        repo_root() / "testlib.h",
    ]
    source = next(
        (candidate for candidate in candidates if candidate.exists() and candidate.is_file()),
        None,
    )
    if source is None:
        return
    target_root_testlib = target / "testlib.h"
    target_problem_testlib = target / "problems" / "testlib.h"
    if not target_root_testlib.exists():
        shutil.copy2(source, target_root_testlib)
    if not target_problem_testlib.exists():
        shutil.copy2(source, target_problem_testlib)


def install_problem_source_package(
    package_root: Path,
    *,
    repository: str | None = None,
    ref: str | None = None,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """설치 문제 소스 package 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        package_root (Path): 설치할 문제 소스 패키지의 루트 디렉터리입니다.
        repository (str | None): GitHub owner/name 또는 URL에서 정규화할 저장소 식별자입니다.
        ref (str | None): GitHub API나 Git 명령에서 사용할 브랜치, 태그, 커밋 참조입니다.
        commit_sha (str | None): 설치한 소스 아카이브의 원본 커밋 SHA입니다.

    Returns:
        dict[str, Any]: 설치 위치, 출처, 문제 개수, 신뢰 경고를 담은 source package
            설치 결과입니다.
    """
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
