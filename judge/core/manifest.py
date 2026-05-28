"""manifest 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from judge.core.config import COMPILE_FLAGS, PROTOCOL_VERSION
from judge.core.paths import repo_root
from judge.core.problem import load_problem, tool_paths
from judge.utils.fs import read_json
from judge.utils.hashing import sha256_file, sha256_json

FILE_HASH_CACHE: dict[Path, tuple[int, int, str]] = {}


def cached_sha256_file(path: Path) -> str:
    """cached_sha256_file 함수를 실행하고 결과를 반환합니다.
    
    Args:
        path (Path): 경로 문자열입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    resolved = path.resolve()
    stat = resolved.stat()
    cached = FILE_HASH_CACHE.get(resolved)
    if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    digest = sha256_file(resolved)
    FILE_HASH_CACHE[resolved] = (stat.st_mtime_ns, stat.st_size, digest)
    return digest


def source_hashes(problem_id: str, root: Path | None = None) -> dict[str, str]:
    """source_hashes 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        dict[str, str]: 처리 결과를 반환합니다.
    """
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
    """generation_key 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str): `profile` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
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
    """validate_manifest 함수를 실행하고 결과를 반환합니다.
    
    Args:
        cache_dir (Path): `cache_dir` 값입니다.
        problem_id (str): 문제 ID입니다.
        profile (str): `profile` 값입니다.
        key (str): `key` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
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
    """validate_manifest_fast 함수를 실행하고 결과를 반환합니다.
    
    Args:
        cache_dir (Path): `cache_dir` 값입니다.
        problem_id (str): 문제 ID입니다.
        profile (str): `profile` 값입니다.
        key (str): `key` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
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
    """build_manifest 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        profile (str): `profile` 값입니다.
        key (str): `key` 값입니다.
        source_hashes_data (dict[str, str]): `source_hashes_data` 값입니다.
        case_summaries (list[dict[str, Any]]): `case_summaries` 값입니다.
        final_dir (Path): `final_dir` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
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
