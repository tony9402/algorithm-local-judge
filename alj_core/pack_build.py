"""문제팩 build 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

import tarfile
import tempfile
from pathlib import Path

from alj_core import __version__
from alj_core.checksums import write_sha256_sidecar
from alj_core.errors import JudgeError
from alj_core.pack_archive import PACK_SCHEMA_VERSION
from alj_core.pack_copy import copy_problem_into_pack
from alj_core.pack_metadata import (
    PackBuildResult,
    manifest_files,
    sanitize_problem_metadata,
)
from alj_core.pack_verify import verify_pack_dir
from alj_core.paths import current_platform_id, repo_root, validate_safe_id
from alj_core.problem import load_problem
from alj_core.solution_validation import verify_problem_solutions
from alj_core.utils.fs import write_json

__all__ = [
    "PackBuildResult",
    "build_pack",
    "build_pack_for_problem_ids",
    "copy_problem_into_pack",
    "manifest_files",
    "sanitize_problem_metadata",
    "write_pack_checksum",
]


def write_pack_checksum(archive_path: Path) -> Path:
    """문제팩 체크섬 데이터를 지정된 파일이나 응답 대상에 기록합니다.

    Args:
        archive_path (Path): 아카이브 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.

    Returns:
        Path: 검증된 문제팩 체크섬 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    return write_sha256_sidecar(archive_path)


def build_pack(
    problem_path: Path,
    pack_id: str,
    platform_id: str | None = None,
    output_dir: Path | None = None,
    verify_profile: str = "hidden",
    warmup_profile: str | None = None,
) -> PackBuildResult:
    """문제팩에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Args:
        problem_path (Path): 문제 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        pack_id (str): 설치, 삭제, 조회할 문제팩을 구분하는 ID입니다.
        platform_id (str | None): platform ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.
        output_dir (Path | None): 출력 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        verify_profile (str): 문제팩을 계산하거나 검증할 때 필요한 verify 프로필 입력입니다.
        warmup_profile (str | None): 문제팩을 계산하거나 검증할 때 필요한 워밍업 프로필 입력입니다.
    """
    problem_path = problem_path.resolve()
    if not (problem_path / "problem.json").exists():
        raise JudgeError(f"problem metadata not found: {problem_path / 'problem.json'}")
    problem_id = problem_path.name
    root = problem_path.parent.parent if problem_path.parent.name == "problems" else repo_root()
    return build_pack_for_problem_ids(
        [problem_id],
        pack_id,
        platform_id,
        output_dir,
        root,
        verify_profile,
        warmup_profile=warmup_profile,
    )


def build_pack_for_problem_ids(
    problem_ids: list[str],
    pack_id: str,
    platform_id: str | None = None,
    output_dir: Path | None = None,
    root: Path | None = None,
    verify_profile: str = "hidden",
    solution_checks: list[dict[str, object]] | None = None,
    warmup_profile: str | None = None,
) -> PackBuildResult:
    """문제팩 문제 ids 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        problem_ids (list[str]): 문제팩 문제 ids을 계산하거나 검증할 때 필요한 문제 ids 입력입니다.
        pack_id (str): 설치, 삭제, 조회할 문제팩을 구분하는 ID입니다.
        platform_id (str | None): platform ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.
        output_dir (Path | None): 출력 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
        verify_profile (str): 문제팩 문제 ids을 계산하거나 검증할 때 필요한 verify 프로필 입력입니다.
        solution_checks (list[dict[str, object]] | None): 문제팩 문제 ids을 계산하거나 검증할 때 필요한 솔루션 검사 입력입니다.
        warmup_profile (str | None): 문제팩 문제 ids을 계산하거나 검증할 때 필요한 워밍업 프로필 입력입니다.
    """
    validate_safe_id("pack id", pack_id)
    if not problem_ids:
        raise JudgeError("problem pack must contain at least one problem")
    root = root or repo_root()
    normalized_problem_ids = []
    for problem_id in problem_ids:
        validate_safe_id("problem id", problem_id)
        if problem_id not in normalized_problem_ids:
            normalized_problem_ids.append(problem_id)
    platform_id = platform_id or current_platform_id()
    if platform_id != current_platform_id():
        raise JudgeError(
            "cross-platform pack build is not implemented yet; "
            f"current platform is {current_platform_id()}, requested {platform_id}"
        )
    metadata_by_problem = {
        problem_id: load_problem(problem_id, root)[2] for problem_id in normalized_problem_ids
    }
    version = (
        str(next(iter(metadata_by_problem.values())).get("version", __version__))
        if len(normalized_problem_ids) == 1
        else __version__
    )
    if solution_checks is None:
        solution_checks = []
        for problem_id in normalized_problem_ids:
            solution_verification = verify_problem_solutions(
                problem_id,
                verify_profile,
                root,
                warmup_profile=warmup_profile,
            )
            solution_checks.extend(check.to_dict(root) for check in solution_verification.checks)
    output_dir = output_dir or repo_root() / "dist" / "packs"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{pack_id}-{version}-{platform_id}.aljpack"

    with tempfile.TemporaryDirectory(prefix="alj-pack-build-") as tmp:
        stage = Path(tmp) / pack_id
        write_json(
            stage / "pack.json",
            {
                "schemaVersion": PACK_SCHEMA_VERSION,
                "packId": pack_id,
                "name": f"{pack_id} problem pack",
                "version": version,
                "engineVersion": __version__,
                "supportedPlatforms": [platform_id],
                "problems": normalized_problem_ids,
            },
        )
        for problem_id in normalized_problem_ids:
            copy_problem_into_pack(problem_id, stage / "problems" / problem_id, platform_id, root)
        write_json(
            stage / "manifest.json",
            {
                "schemaVersion": PACK_SCHEMA_VERSION,
                "packId": pack_id,
                "version": version,
                "platformId": platform_id,
                "files": manifest_files(stage),
            },
        )
        verify_pack_dir(stage)
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(stage, arcname=pack_id)
    write_pack_checksum(archive_path)
    return PackBuildResult(
        archive_path,
        pack_id,
        platform_id,
        normalized_problem_ids,
        solution_checks,
    )
