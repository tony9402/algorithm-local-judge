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
    """Return profile names declared by a problem generator config."""
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
    """Return problem metadata for the web UI."""
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
    """Return installed problem pack metadata."""
    return installed_packs()


def current_web_config() -> dict[str, Any]:
    """Return web configuration values that the UI should display."""
    return {
        "officialRepository": official_pack_repository(),
        "sampleProfile": SAMPLE_PROFILE,
        "judgeProfile": FULL_PROFILE,
        "webDebug": web_debug_enabled(),
    }


def dashboard_status() -> dict[str, Any]:
    """Return the initial dashboard status for the web UI."""
    return {
        "problems": list_problems(),
        "packs": list_packs(),
        "cache": cache_status(),
        "config": current_web_config(),
    }
