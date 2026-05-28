"""service_cache 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from typing import Any

from judge.core.cache import build_cache_clear_plan, cache_status_data, delete_cache_targets
from judge.core.paths import rel
from judge.utils.text import format_size


def cache_status() -> dict[str, Any]:
    """cache_status 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    data = cache_status_data()
    data["totalSizeLabel"] = format_size(int(data["totalSize"]))
    runs = data["runs"]
    if isinstance(runs, dict):
        runs["sizeLabel"] = format_size(int(runs["size"]))
    sources = data.get("sources")
    if isinstance(sources, dict):
        sources["sizeLabel"] = format_size(int(sources["size"]))
    for problem in data["problems"]:
        problem["sizeLabel"] = format_size(int(problem["size"]))
    return data


def cache_clear(
    problem: str | None,
    profile: str | None,
    runs: bool,
    all_entries: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """cache_clear 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem (str | None): `problem` 값입니다.
        profile (str | None): `profile` 값입니다.
        runs (bool): `runs` 값입니다.
        all_entries (bool): `all_entries` 값입니다.
        dry_run (bool): `dry_run` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    plan = build_cache_clear_plan(problem, profile, runs, all_entries)
    targets = [
        {
            "path": str(target),
            "label": rel(target, plan.root),
        }
        for target in plan.targets
    ]
    if not dry_run:
        delete_cache_targets(plan.targets, plan.operation_root)
    return {
        "dryRun": dry_run,
        "deleted": not dry_run,
        "totalSize": plan.total_size,
        "totalSizeLabel": format_size(plan.total_size),
        "targets": targets,
    }
