"""캐시 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import cache_root, ensure_inside, rel, repo_root, validate_safe_id
from judge.utils.fs import path_size, read_json
from judge.utils.text import format_size


@dataclass
class CacheClearPlan:
    """캐시 clear plan 상태와 관련 동작을 하나의 객체로 표현합니다."""

    root: Path
    targets: list[Path]
    total_size: int
    operation_root: Path | None = None


def cache_status_data(root: Path | None = None) -> dict[str, object]:
    base = cache_root(root)
    problems = base / "problems"
    runs = base / "runs"
    sources = base / "web-submissions"
    problem_entries = []
    if problems.exists():
        for problem_dir in sorted(path for path in problems.iterdir() if path.is_dir()):
            caches = [path for path in problem_dir.iterdir() if path.is_dir()]
            problem_entries.append(
                {
                    "problemId": problem_dir.name,
                    "cacheCount": len(caches),
                    "size": path_size(problem_dir),
                }
            )
    run_entries = [path for path in runs.iterdir() if path.is_dir()] if runs.exists() else []
    source_entries = (
        [path for path in sources.iterdir() if path.is_dir()] if sources.exists() else []
    )
    return {
        "path": str(base),
        "exists": base.exists(),
        "totalSize": path_size(base),
        "problems": problem_entries,
        "runs": {"count": len(run_entries), "size": path_size(runs)},
        "sources": {"count": len(source_entries), "size": path_size(sources)},
    }


def cache_status(root: Path | None = None) -> None:
    base = cache_root(root)
    display_root = root or repo_root()
    problems = base / "problems"
    runs = base / "runs"
    sources = base / "web-submissions"
    print(f"cache: {rel(base, display_root)}")
    if not base.exists():
        print("status: empty")
        return
    total = path_size(base)
    print(f"total size: {format_size(total)}")
    if problems.exists():
        for problem_dir in sorted(path for path in problems.iterdir() if path.is_dir()):
            entries = [path for path in problem_dir.iterdir() if path.is_dir()]
            size = format_size(path_size(problem_dir))
            print(f"problem {problem_dir.name}: {len(entries)} cache(s), {size}")
    else:
        print("problem caches: 0")
    if runs.exists():
        entries = [path for path in runs.iterdir() if path.is_dir()]
        print(f"runs: {len(entries)} run(s), {format_size(path_size(runs))}")
    else:
        print("runs: 0")
    if sources.exists():
        entries = [path for path in sources.iterdir() if path.is_dir()]
        print(f"sources: {len(entries)} source(s), {format_size(path_size(sources))}")
    else:
        print("sources: 0")


def clear_targets(
    problem: str | None = None,
    profile: str | None = None,
    runs: bool = False,
    all_entries: bool = False,
    root: Path | None = None,
) -> list[Path]:
    """targets 캐시, 선택 상태, 또는 화면 표시를 초기화합니다.

    Args:
        problem (str | None): targets을 계산하거나 검증할 때 필요한 문제 입력입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        runs (bool): targets 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        all_entries (bool): targets 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.

    Returns:
        list[Path]: 검증된 targets 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    base = cache_root(root)
    targets = []
    if problem:
        validate_safe_id("problem id", problem)
    if profile:
        validate_safe_id("profile", profile)
    if all_entries:
        targets.append(base)
    else:
        if problem:
            problem_base = base / "problems" / problem
            if profile:
                if problem_base.exists():
                    for cache_dir in problem_base.iterdir():
                        manifest = cache_dir / "manifest.json"
                        if manifest.exists():
                            try:
                                if read_json(manifest).get("profile") == profile:
                                    targets.append(cache_dir)
                            except json.JSONDecodeError:
                                continue
            else:
                targets.append(problem_base)
        if runs:
            targets.append(base / "runs")
            targets.append(base / "web-submissions")
            targets.append(base / "web-uploads" / "sources")
    return [ensure_inside(path, base) for path in targets if path.exists()]


def build_cache_clear_plan(
    problem: str | None = None,
    profile: str | None = None,
    runs: bool = False,
    all_entries: bool = False,
    root: Path | None = None,
) -> CacheClearPlan:
    """캐시 clear plan에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Args:
        problem (str | None): 캐시 clear plan을 계산하거나 검증할 때 필요한 문제 입력입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        runs (bool): 캐시 clear plan 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        all_entries (bool): 캐시 clear plan 흐름에서 해당 조건을 적용할지 결정하는 플래그입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
    """
    targets = clear_targets(problem, profile, runs, all_entries, root)
    return CacheClearPlan(
        root=cache_root(root),
        targets=targets,
        total_size=sum(path_size(path) for path in targets),
        operation_root=root,
    )


def delete_cache_targets(targets: list[Path], root: Path | None = None) -> None:
    """캐시 targets 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        targets (list[Path]): 캐시 targets을 계산하거나 검증할 때 필요한 targets 입력입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
    """
    base = cache_root(root)
    display_root = root or repo_root()
    lock = base / ".lock"
    if lock.exists():
        raise JudgeError(f"cache is locked: {rel(lock, display_root)}")
    for path in targets:
        path = ensure_inside(path, base)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
