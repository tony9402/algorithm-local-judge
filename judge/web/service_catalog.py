"""service_catalog 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from typing import Any

from commons.generate import load_config
from judge.core.pack import installed_packs
from judge.core.problem import discover_problem_ids, load_problem, tool_paths
from judge.core.problem_folders import problem_folder_payload
from judge.core.remote import official_pack_repository
from judge.web.service_cache import cache_status
from judge.web.service_common import FULL_PROFILE, SAMPLE_PROFILE, web_debug_enabled


def problem_profiles(problem_id: str) -> list[str]:
    """problem_profiles 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
    
    Returns:
        list[str]: 처리 결과를 반환합니다.
    """
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
    """list_problems 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        list[dict[str, Any]]: 처리 결과를 반환합니다.
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
    """list_packs 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        list[dict[str, Any]]: 처리 결과를 반환합니다.
    """
    return installed_packs()


def current_web_config() -> dict[str, Any]:
    """current_web_config 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    return {
        "officialRepository": official_pack_repository(),
        "sampleProfile": SAMPLE_PROFILE,
        "judgeProfile": FULL_PROFILE,
        "webDebug": web_debug_enabled(),
    }


def dashboard_status() -> dict[str, Any]:
    """dashboard_status 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    return {
        "problems": list_problems(),
        "packs": list_packs(),
        "cache": cache_status(),
        "config": current_web_config(),
    }
