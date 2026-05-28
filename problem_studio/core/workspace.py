"""작업 공간 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.paths import ensure_inside, rel, repo_root, validate_safe_id
from judge.core.problem import load_problem
from judge.core.problem_discovery import problem_sort_key
from judge.utils.fs import write_json

DELETE_CONFIRM_PHRASE = "확인했습니다"


def resolve_workspace(path: Path | str | None = None) -> Path:
    """작업 공간 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        path (Path | str | None): 읽기, 쓰기, 검증, 표시 대상이 되는 파일 또는 디렉터리 경로입니다.

    Returns:
        Path: 검증된 작업 공간 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    workspace = Path(path or ".").expanduser().resolve()
    if workspace.name == "problems":
        workspace = workspace.parent
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "problems").mkdir(parents=True, exist_ok=True)
    return workspace


def problems_dir(workspace: Path) -> Path:
    return workspace / "problems"


def problem_dir(workspace: Path, problem_id: str) -> Path:
    validate_safe_id("problem id", problem_id)
    path = problems_dir(workspace) / problem_id
    return ensure_inside(path, problems_dir(workspace))


def discover_workspace_problem_ids(workspace: Path) -> list[str]:
    """설정과 디렉터리를 탐색해 사용 가능한 작업 공간 문제 ids 항목을 찾습니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.

    Returns:
        list[str]: 호출자가 순회하거나 화면에 표시할 작업 공간 문제 ids 항목 목록입니다.
    """
    root = problems_dir(workspace)
    if not root.exists():
        return []
    return sorted(
        {path.parent.name for path in root.glob("*/problem.json")},
        key=problem_sort_key,
    )


def discover_source_root(workspace: Path) -> Path:
    """설정과 디렉터리를 탐색해 사용 가능한 소스 root 항목을 찾습니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.

    Returns:
        Path: 검증된 소스 root 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    configured = os.environ.get("JUDGE_SOURCE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = [
        workspace,
        workspace.parent / "algorithm-local-judge",
        repo_root(),
    ]
    for candidate in candidates:
        if (candidate / "testlib.h").exists():
            return candidate.resolve()
    return repo_root()


def testlib_status(workspace: Path) -> dict[str, Any]:
    source_root = discover_source_root(workspace)
    source = source_root / "testlib.h"
    workspace_link = problems_dir(workspace) / "testlib.h"
    return {
        "sourceRoot": str(source_root),
        "sourceExists": source.exists(),
        "workspacePath": str(workspace_link),
        "workspaceExists": workspace_link.exists(),
        "isSymlink": workspace_link.is_symlink(),
        "target": str(workspace_link.resolve()) if workspace_link.exists() else None,
    }


def link_testlib(workspace: Path) -> dict[str, Any]:
    """link testlib 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 link testlib 데이터입니다.
    """
    source = discover_source_root(workspace) / "testlib.h"
    if not source.exists():
        raise JudgeError(f"testlib.h not found: {source}")
    target = problems_dir(workspace) / "testlib.h"
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        raise JudgeError(f"refusing to replace non-symlink testlib.h: {target}")
    target.symlink_to(source)
    return testlib_status(workspace)


def list_problem_metadata(workspace: Path) -> list[dict[str, Any]]:
    """현재 설정과 파일시스템을 기준으로 문제 메타데이터 목록을 조회합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.

    Returns:
        list[dict[str, Any]]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 메타데이터 데이터입니다.
    """
    problems = []
    for problem_id in discover_workspace_problem_ids(workspace):
        _, metadata_path, metadata = load_problem(problem_id, workspace)
        problems.append(
            {
                "problemId": problem_id,
                "title": metadata.get("title", ""),
                "version": metadata.get("version", ""),
                "defaultProfile": metadata.get("defaultProfile", "hidden"),
                "folder": metadata.get("folder", ""),
                "path": str(metadata_path.parent),
                "label": rel(metadata_path.parent, workspace),
            }
        )
    return problems


def problem_folders(problems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for problem in problems:
        folder = str(problem.get("folder") or "").strip()
        counts[folder] = counts.get(folder, 0) + 1
    return [
        {
            "name": folder,
            "label": folder or "기본",
            "problemCount": counts[folder],
        }
        for folder in sorted(counts, key=lambda value: (value == "", value.lower()))
    ]


def delete_problem(
    workspace: Path,
    problem_id: str,
    confirm_phrase: str,
) -> dict[str, Any]:
    """문제 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        confirm_phrase (str): 문제을 계산하거나 검증할 때 필요한 confirm phrase 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 데이터입니다.
    """
    if confirm_phrase != DELETE_CONFIRM_PHRASE:
        raise JudgeError(f'문제를 삭제하려면 "{DELETE_CONFIRM_PHRASE}"를 정확히 입력하세요.')
    target = problem_dir(workspace, problem_id)
    if not target.exists():
        raise JudgeError(f"problem not found: {problem_id}")
    if not (target / "problem.json").exists():
        raise JudgeError(f"refusing to delete non-problem directory: {rel(target, workspace)}")
    shutil.rmtree(target)
    return {
        "deleted": True,
        "problemId": problem_id,
        "workspace": workspace_status(workspace),
    }


def rename_problem(
    workspace: Path,
    problem_id: str,
    new_problem_id: str,
) -> dict[str, Any]:
    validate_safe_id("problem id", new_problem_id)
    if problem_id == new_problem_id:
        _, metadata_path, metadata = load_problem(problem_id, workspace)
        return {
            "problemId": problem_id,
            "previousProblemId": problem_id,
            "path": str(metadata_path.parent),
            "metadata": metadata,
            "workspace": workspace_status(workspace),
        }

    source = problem_dir(workspace, problem_id)
    target = problem_dir(workspace, new_problem_id)
    if not source.exists():
        raise JudgeError(f"problem not found: {problem_id}")
    if not (source / "problem.json").exists():
        raise JudgeError(f"refusing to rename non-problem directory: {rel(source, workspace)}")
    if target.exists():
        raise JudgeError(f"problem already exists: {new_problem_id}")

    _, metadata_path, metadata = load_problem(problem_id, workspace)
    previous_metadata = dict(metadata)
    metadata = {**metadata, "problemId": new_problem_id}
    write_json(metadata_path, metadata)
    try:
        source.rename(target)
    except Exception:
        write_json(metadata_path, previous_metadata)
        raise

    return {
        "problemId": new_problem_id,
        "previousProblemId": problem_id,
        "path": str(target),
        "metadata": metadata,
        "workspace": workspace_status(workspace),
    }


def workspace_status(workspace: Path) -> dict[str, Any]:
    problem_ids = discover_workspace_problem_ids(workspace)
    problems = list_problem_metadata(workspace)
    return {
        "workspace": str(workspace),
        "problemsDir": str(problems_dir(workspace)),
        "problemIds": problem_ids,
        "problemCount": len(problem_ids),
        "testlib": testlib_status(workspace),
        "problems": problems,
        "folders": problem_folders(problems),
    }
