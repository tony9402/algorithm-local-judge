"""서비스 카탈로그 웹 백엔드 구성과 응답 데이터 조립을 담당합니다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from commons.generate import load_config
from judge.core.errors import JudgeError
from judge.core.pack import installed_packs, remove_all_packs, remove_pack
from judge.core.paths import ensure_inside, problem_pack_root, validate_safe_id
from judge.core.problem import discover_problem_ids, load_problem, tool_paths
from judge.core.problem_folders import list_problem_folders, problem_folder_payload
from judge.core.remote import official_pack_repository
from judge.web.service_cache import cache_status
from judge.web.service_common import FULL_PROFILE, SAMPLE_PROFILE, web_debug_enabled

REMOVE_ALL_PACKS_CONFIRMATION = "모두 제거"


def problem_profiles(problem_id: str) -> list[str]:
    try:
        _, _, _, paths = tool_paths(problem_id)
        config = load_config(paths["generatorConfig"])
    except Exception:
        return []
    profiles = config.get("profiles", {})
    if not isinstance(profiles, dict):
        return []
    names = sorted(profiles)
    return names if FULL_PROFILE in profiles else [FULL_PROFILE, *names]


def list_problems() -> list[dict[str, Any]]:
    """현재 설정과 파일시스템을 기준으로 문제 목록을 조회합니다.

    Returns:
        list[dict[str, Any]]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 데이터입니다.
    """
    problems = []
    for problem_id in discover_problem_ids():
        problem_dir, _, metadata = load_problem(problem_id)
        problems.append(
            {
                "problemId": problem_id,
                "title": metadata.get("title", ""),
                "version": metadata.get("version"),
                "defaultProfile": metadata.get("defaultProfile", "full"),
                "profiles": problem_profiles(problem_id),
                **problem_folder_payload(metadata, problem_dir),
            }
        )
    return problems


def list_packs() -> list[dict[str, Any]]:
    """현재 설정과 파일시스템을 기준으로 문제팩 목록을 조회합니다.

    Returns:
        list[dict[str, Any]]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제팩 데이터입니다.
    """
    return installed_packs()


def remove_problem_pack(pack_id: str, confirmation: str) -> dict[str, Any]:
    """정확한 팩 ID 확인 후 설치된 팩과 그 팩이 제공한 문제만 제거합니다."""
    validate_safe_id("pack id", pack_id)
    if confirmation != pack_id:
        raise JudgeError("문제 팩 ID를 정확히 입력해야 제거할 수 있습니다.")
    pack_root = problem_pack_root().resolve()
    target = ensure_inside(pack_root / pack_id, pack_root)
    pack = next(
        (
            item
            for item in installed_packs()
            if item.get("packId") == pack_id
            and isinstance(item.get("path"), str)
            and ensure_inside(Path(item["path"]), pack_root) == target
        ),
        None,
    )
    if pack is None:
        raise JudgeError(f"problem pack not installed: {pack_id}")
    problems = pack.get("problems", [])
    removed_problems = [str(item) for item in problems] if isinstance(problems, list) else []
    remove_pack(pack_id)
    return {
        "removed": True,
        "packId": pack_id,
        "removedProblems": removed_problems,
        "removedProblemCount": len(removed_problems),
    }


def remove_all_problem_packs(confirmation: str) -> dict[str, Any]:
    """명시적 확인 후 설치된 모든 문제 팩을 제거하고 보존 범위를 보고합니다."""
    if confirmation != REMOVE_ALL_PACKS_CONFIRMATION:
        raise JudgeError(
            f'모든 문제 팩을 제거하려면 "{REMOVE_ALL_PACKS_CONFIRMATION}"를 입력하세요.'
        )
    removed_packs = remove_all_packs()
    removed_problem_count = sum(
        len(pack.get("problems", []))
        for pack in removed_packs
        if isinstance(pack.get("problems"), list)
    )
    return {
        "removed": True,
        "removedPackIds": [str(pack.get("packId")) for pack in removed_packs],
        "removedPackCount": len(removed_packs),
        "removedProblemCount": removed_problem_count,
        "preserved": ["submissions", "source-history", "problem-sources"],
    }


def current_web_config() -> dict[str, Any]:
    return {
        "officialRepository": official_pack_repository(),
        "sampleProfile": SAMPLE_PROFILE,
        "judgeProfile": FULL_PROFILE,
        "webDebug": web_debug_enabled(),
    }


def dashboard_status() -> dict[str, Any]:
    return {
        "problems": list_problems(),
        "folders": list_problem_folders(),
        "packs": list_packs(),
        "cache": cache_status(),
        "config": current_web_config(),
    }
