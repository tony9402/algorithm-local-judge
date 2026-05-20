from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.paths import ensure_inside, rel, repo_root, validate_safe_id
from judge.core.problem import discover_problem_ids, load_problem
from judge.utils.fs import write_json

DELETE_CONFIRM_PHRASE = "확인했습니다"


def resolve_workspace(path: Path | str | None = None) -> Path:
    """Return a normalized workspace root for a problem repository."""
    workspace = Path(path or ".").expanduser().resolve()
    if workspace.name == "problems":
        workspace = workspace.parent
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "problems").mkdir(parents=True, exist_ok=True)
    return workspace


def problems_dir(workspace: Path) -> Path:
    """Return the problems directory for a workspace."""
    return workspace / "problems"


def problem_dir(workspace: Path, problem_id: str) -> Path:
    """Return a validated problem directory path."""
    validate_safe_id("problem id", problem_id)
    path = problems_dir(workspace) / problem_id
    return ensure_inside(path, problems_dir(workspace))


def discover_source_root(workspace: Path) -> Path:
    """Return the common judge source root used for testlib.h and core commands."""
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
    """Return whether testlib.h is visible from the problem workspace."""
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
    """Expose the common testlib.h under problems/testlib.h as a symlink."""
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
    """Return discovered problem metadata for the studio UI."""
    problems = []
    for problem_id in discover_problem_ids(workspace):
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
    """Return folder summaries for the problem sidebar."""
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
    """Delete a problem directory only after the exact confirmation phrase."""
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
    """Rename a problem directory and keep problem.json in sync."""
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
    """Return a structured summary of the current problem authoring workspace."""
    problem_ids = discover_problem_ids(workspace)
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
