"""매니페스트 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alj_core.config import COMPILE_FLAGS, PROTOCOL_VERSION
from alj_core.paths import repo_root
from alj_core.problem import load_problem, tool_paths
from alj_core.utils.fs import read_json
from alj_core.utils.hashing import sha256_file, sha256_json

FILE_HASH_CACHE: dict[Path, tuple[int, int, str]] = {}


def cached_sha256_file(path: Path) -> str:
    resolved = path.resolve()
    stat = resolved.stat()
    cached = FILE_HASH_CACHE.get(resolved)
    if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    digest = sha256_file(resolved)
    FILE_HASH_CACHE[resolved] = (stat.st_mtime_ns, stat.st_size, digest)
    return digest


def source_hashes(problem_id: str, root: Path | None = None) -> dict[str, str]:
    _, metadata_path, _, paths = tool_paths(problem_id, root)
    project_root = root or repo_root()
    hashes = {
        "problem": cached_sha256_file(metadata_path),
        "generatorConfig": cached_sha256_file(paths["generatorConfig"]),
        "generator": cached_sha256_file(paths["generator"]),
        "validator": cached_sha256_file(paths["validator"]),
        "checker": cached_sha256_file(paths["checker"]),
        "solution": cached_sha256_file(paths["solution"]),
    }
    testlib = project_root / "testlib.h"
    if testlib.exists():
        hashes["testlib"] = cached_sha256_file(testlib)
    common_generator = project_root / "commons" / "generate.py"
    if common_generator.exists():
        hashes["commonGeneratorScript"] = cached_sha256_file(common_generator)
    return hashes


def generation_key(problem_id: str, profile: str, root: Path | None = None) -> str:
    _, _, metadata = load_problem(problem_id, root)
    payload = {
        "protocolVersion": PROTOCOL_VERSION,
        "compileFlags": COMPILE_FLAGS,
        "compiler": "g++",
        "schemaVersion": metadata.get("schemaVersion"),
        "problemId": problem_id,
        "problemVersion": metadata.get("version"),
        "profile": profile,
        "sourceHashes": source_hashes(problem_id, root),
    }
    return sha256_json(payload)[:24]


def validate_manifest(cache_dir: Path, problem_id: str, profile: str, key: str) -> bool:
    """매니페스트 값이 허용되는 형식과 정책을 만족하는지 검사합니다.

    Args:
        cache_dir (Path): 캐시 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        key (str): 상태 맵, 로컬 스토리지, 객체에서 값을 찾는 키입니다.

    Returns:
        bool: 매니페스트 조건을 만족하면 True, 아니면 False입니다.
    """
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = read_json(manifest_path)
    except json.JSONDecodeError:
        return False
    if manifest.get("problemId") != problem_id:
        return False
    if manifest.get("profile") != profile:
        return False
    if manifest.get("generationKey") != key:
        return False
    for case in manifest.get("cases", []):
        in_path = cache_dir / case["input"]
        out_path = cache_dir / case["answer"]
        if not in_path.exists() or not out_path.exists():
            return False
        if sha256_file(in_path) != case.get("inputHash"):
            return False
        if sha256_file(out_path) != case.get("answerHash"):
            return False
    return True


def validate_manifest_fast(cache_dir: Path, problem_id: str, profile: str, key: str) -> bool:
    """매니페스트 fast 값이 허용되는 형식과 정책을 만족하는지 검사합니다.

    Args:
        cache_dir (Path): 캐시 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        key (str): 상태 맵, 로컬 스토리지, 객체에서 값을 찾는 키입니다.

    Returns:
        bool: 매니페스트 fast 조건을 만족하면 True, 아니면 False입니다.
    """
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = read_json(manifest_path)
    except json.JSONDecodeError:
        return False
    if manifest.get("problemId") != problem_id:
        return False
    if manifest.get("profile") != profile:
        return False
    if manifest.get("generationKey") != key:
        return False
    for case in manifest.get("cases", []):
        if not (cache_dir / case["input"]).exists():
            return False
        if not (cache_dir / case["answer"]).exists():
            return False
    return True


def build_manifest(
    problem_id: str,
    profile: str,
    key: str,
    source_hashes_data: dict[str, str],
    case_summaries: list[dict[str, Any]],
    final_dir: Path,
    root: Path | None = None,
) -> dict[str, Any]:
    """매니페스트에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        profile (str): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        key (str): 상태 맵, 로컬 스토리지, 객체에서 값을 찾는 키입니다.
        source_hashes_data (dict[str, str]): 매니페스트을 계산하거나 검증할 때 필요한 소스 hashes 데이터 입력입니다.
        case_summaries (list[dict[str, Any]]): 매니페스트을 계산하거나 검증할 때 필요한 케이스 summaries 입력입니다.
        final_dir (Path): final dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 매니페스트 데이터입니다.
    """
    _, _, metadata = load_problem(problem_id, root)
    cases = []
    for case in case_summaries:
        input_rel = f"cases/{case['id']}.in"
        answer_rel = f"cases/{case['id']}.out"
        in_path = final_dir / input_rel
        out_path = final_dir / answer_rel
        cases.append(
            {
                "id": case["id"],
                "name": case.get("name", case["id"]),
                "seed": case.get("seed"),
                "method": case.get("method", "unknown"),
                "input": input_rel,
                "answer": answer_rel,
                "inputHash": sha256_file(in_path),
                "answerHash": sha256_file(out_path),
            }
        )
    return {
        "schemaVersion": 1,
        "protocolVersion": PROTOCOL_VERSION,
        "problemId": problem_id,
        "problemVersion": metadata.get("version"),
        "profile": profile,
        "generationKey": key,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sourceHashes": source_hashes_data,
        "cases": cases,
    }
