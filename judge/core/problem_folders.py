"""문제 폴더 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError, SecurityPolicyError
from judge.core.paths import rel, user_data_root
from judge.core.problem_discovery import discover_problem_ids, problem_roots
from judge.core.problem_metadata import load_problem

MAX_FOLDER_LENGTH = 80
FOLDER_REGISTRY_NAME = "judge-folders.json"
FOLDER_DELETE_WARNING = "폴더 내 문제들이 모두 삭제됩니다."


def normalize_problem_folder(folder: str | None) -> str:
    """문제 폴더 입력을 비교와 저장에 쓰기 쉬운 표준 형식으로 정규화합니다.

    Args:
        folder (str | None): 문제 폴더을 계산하거나 검증할 때 필요한 폴더 입력입니다.

    Returns:
        str: 정책 검사를 통과한 표준 문제 폴더 문자열입니다.
    """
    value = (folder or "").strip()
    if len(value) > MAX_FOLDER_LENGTH:
        raise JudgeError(f"problem folder is too long (max {MAX_FOLDER_LENGTH} characters)")
    if any(ord(char) < 32 for char in value):
        raise JudgeError("problem folder cannot contain control characters")
    return value


def problem_folder_editable(problem_dir: Path) -> bool:
    resolved = problem_dir.resolve()
    metadata_path = resolved / "problem.json"
    return metadata_path.exists() and metadata_path.is_file()


def problem_folder_registry_path() -> Path:
    return user_data_root() / FOLDER_REGISTRY_NAME


def read_problem_folder_registry() -> list[str]:
    path = problem_folder_registry_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    folders = data.get("folders") if isinstance(data, dict) else data
    if not isinstance(folders, list):
        return []
    result = []
    seen = set()
    for folder in folders:
        if not isinstance(folder, str):
            continue
        normalized = normalize_problem_folder(folder)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def write_problem_folder_registry(folders: list[str]) -> None:
    normalized = []
    seen = set()
    for folder in folders:
        value = normalize_problem_folder(folder)
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    path = problem_folder_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"folders": sorted(normalized, key=str.lower)}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def problem_folder_items() -> list[tuple[str, Path, dict[str, Any]]]:
    items = []
    for problem_id in discover_problem_ids():
        problem_dir, _metadata_path, metadata = load_problem(problem_id)
        items.append((problem_id, problem_dir, metadata))
    return items


def list_problem_folders() -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    folders = set(read_problem_folder_registry())
    folders.add("")
    for _problem_id, _problem_dir, metadata in problem_folder_items():
        folder = normalize_problem_folder(metadata.get("folder") if isinstance(metadata, dict) else "")
        folders.add(folder)
        counts[folder] = counts.get(folder, 0) + 1
    return [
        {
            "folder": folder,
            "label": folder or "Uncategorized",
            "problemCount": counts.get(folder, 0),
        }
        for folder in sorted(folders, key=lambda value: ((value or "Uncategorized").lower()))
    ]


def create_problem_folder(folder: str | None) -> dict[str, Any]:
    normalized = normalize_problem_folder(folder)
    if not normalized:
        raise JudgeError("problem folder name is required")
    folders = read_problem_folder_registry()
    if normalized not in folders:
        folders.append(normalized)
        write_problem_folder_registry(folders)
    return {"folder": normalized, "folders": list_problem_folders()}


def problems_in_folder(folder: str | None) -> list[dict[str, Any]]:
    normalized = normalize_problem_folder(folder)
    result = []
    for problem_id, problem_dir, metadata in problem_folder_items():
        problem_folder = normalize_problem_folder(metadata.get("folder") if isinstance(metadata, dict) else "")
        if problem_folder == normalized:
            result.append(
                {
                    "problemId": problem_id,
                    "title": metadata.get("title", ""),
                    "path": str(problem_dir),
                }
            )
    return result


def ensure_problem_dir_deletable(problem_dir: Path) -> Path:
    resolved = problem_dir.resolve()
    if not (resolved / "problem.json").is_file():
        raise SecurityPolicyError(f"refusing to delete non-problem directory: {rel(resolved)}")
    roots = [root.resolve() for root in problem_roots()]
    if not any(root == resolved.parent or root in resolved.parents for root in roots):
        raise SecurityPolicyError(f"refusing to delete problem outside known roots: {rel(resolved)}")
    return resolved


def delete_problem_folder(
    folder: str | None,
    *,
    confirm_delete_problems: bool = False,
) -> dict[str, Any]:
    normalized = normalize_problem_folder(folder)
    if not normalized:
        raise JudgeError("default folder cannot be deleted")
    targets = problems_in_folder(normalized)
    if targets and not confirm_delete_problems:
        return {
            "deleted": False,
            "requiresConfirmation": True,
            "folder": normalized,
            "warning": FOLDER_DELETE_WARNING,
            "problems": targets,
        }
    for item in targets:
        shutil.rmtree(ensure_problem_dir_deletable(Path(item["path"])))
    folders = [item for item in read_problem_folder_registry() if item != normalized]
    write_problem_folder_registry(folders)
    return {
        "deleted": True,
        "requiresConfirmation": False,
        "folder": normalized,
        "deletedProblems": [item["problemId"] for item in targets],
        "warning": FOLDER_DELETE_WARNING if targets else "",
        "folders": list_problem_folders(),
    }


def problem_folder_payload(metadata: dict[str, Any], problem_dir: Path) -> dict[str, Any]:
    folder = metadata.get("folder")
    return {
        "folder": folder if isinstance(folder, str) else "",
        "folderEditable": problem_folder_editable(problem_dir),
    }


def update_problem_folder(problem_id: str, folder: str | None) -> dict[str, Any]:
    """문제 폴더 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        folder (str | None): 문제 폴더을 계산하거나 검증할 때 필요한 폴더 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 폴더 데이터입니다.
    """
    problem_dir, metadata_path, metadata = load_problem(problem_id)
    if not problem_folder_editable(problem_dir):
        raise SecurityPolicyError(
            "problem folder cannot be changed because problem metadata is not editable"
        )
    normalized_folder = normalize_problem_folder(folder)
    known_folders = {normalize_problem_folder(item["folder"]) for item in list_problem_folders()}
    if normalized_folder and normalized_folder not in known_folders:
        raise JudgeError("problem folder must be created before moving problems")
    metadata["folder"] = normalized_folder
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "problemId": problem_id,
        "path": rel(metadata_path),
        "metadata": metadata,
        **problem_folder_payload(metadata, problem_dir),
    }
