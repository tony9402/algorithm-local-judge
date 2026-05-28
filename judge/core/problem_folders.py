"""problem_folders 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError, SecurityPolicyError
from judge.core.paths import problem_pack_root, rel
from judge.core.problem_metadata import load_problem

MAX_FOLDER_LENGTH = 80


def normalize_problem_folder(folder: str | None) -> str:
    """normalize_problem_folder 함수를 실행하고 결과를 반환합니다.
    
    Args:
        folder (str | None): `folder` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    value = (folder or "").strip()
    if len(value) > MAX_FOLDER_LENGTH:
        raise JudgeError(f"problem folder is too long (max {MAX_FOLDER_LENGTH} characters)")
    if any(ord(char) < 32 for char in value):
        raise JudgeError("problem folder cannot contain control characters")
    return value


def problem_folder_editable(problem_dir: Path) -> bool:
    """problem_folder_editable 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_dir (Path): `problem_dir` 값입니다.
    
    Returns:
        bool: 처리 결과를 반환합니다.
    """
    resolved = problem_dir.resolve()
    packs = problem_pack_root().resolve()
    if resolved == packs or packs in resolved.parents:
        return False
    metadata_path = resolved / "problem.json"
    return metadata_path.exists() and metadata_path.is_file()


def problem_folder_payload(metadata: dict[str, Any], problem_dir: Path) -> dict[str, Any]:
    """problem_folder_payload 함수를 실행하고 결과를 반환합니다.
    
    Args:
        metadata (dict[str, Any]): `metadata` 값입니다.
        problem_dir (Path): `problem_dir` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    folder = metadata.get("folder")
    return {
        "folder": folder if isinstance(folder, str) else "",
        "folderEditable": problem_folder_editable(problem_dir),
    }


def update_problem_folder(problem_id: str, folder: str | None) -> dict[str, Any]:
    """update_problem_folder 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        folder (str | None): `folder` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    problem_dir, metadata_path, metadata = load_problem(problem_id)
    if not problem_folder_editable(problem_dir):
        raise SecurityPolicyError(
            "problem folder cannot be changed for installed .aljpack problems; "
            "install a source problem package or edit the original problem repository"
        )
    metadata["folder"] = normalize_problem_folder(folder)
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
