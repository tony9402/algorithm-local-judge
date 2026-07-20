"""서비스 캐시 웹 백엔드 구성과 응답 데이터 조립을 담당합니다."""

from __future__ import annotations

from typing import Any

from judge.core.cache import build_cache_clear_plan, cache_status_data, delete_cache_targets
from judge.core.paths import rel
from judge.utils.text import format_size


def cache_status() -> dict[str, Any]:
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
