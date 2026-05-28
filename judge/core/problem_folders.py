"""문제 폴더 도메인 로직과 파일시스템 변경 정책을 담당합니다.
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
    packs = problem_pack_root().resolve()
    if resolved == packs or packs in resolved.parents:
        return False
    metadata_path = resolved / "problem.json"
    return metadata_path.exists() and metadata_path.is_file()


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
