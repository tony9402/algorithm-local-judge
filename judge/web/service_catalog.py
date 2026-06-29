"""서비스 카탈로그 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
"""
from __future__ import annotations

from typing import Any

from commons.generate import load_config
from judge.core.pack import installed_packs
from judge.core.problem import discover_problem_ids, load_problem, tool_paths
from judge.core.problem_folders import list_problem_folders, problem_folder_payload
from judge.core.remote import official_pack_repository
from judge.web.service_cache import cache_status
from judge.web.service_common import FULL_PROFILE, SAMPLE_PROFILE, web_debug_enabled


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
