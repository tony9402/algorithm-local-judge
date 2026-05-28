from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError, SecurityPolicyError
from judge.core.paths import problem_pack_root, rel
from judge.core.problem_metadata import load_problem

MAX_FOLDER_LENGTH = 80


def normalize_problem_folder(folder: str | None) -> str:
    """Return a display folder value safe to persist in problem metadata."""
    value = (folder or "").strip()
    if len(value) > MAX_FOLDER_LENGTH:
        raise JudgeError(f"problem folder is too long (max {MAX_FOLDER_LENGTH} characters)")
    if any(ord(char) < 32 for char in value):
        raise JudgeError("problem folder cannot contain control characters")
    return value


def problem_folder_editable(problem_dir: Path) -> bool:
    """Return whether the problem metadata can be edited by the Judge web UI."""
    resolved = problem_dir.resolve()
    packs = problem_pack_root().resolve()
    if resolved == packs or packs in resolved.parents:
        return False
    metadata_path = resolved / "problem.json"
    return metadata_path.exists() and metadata_path.is_file()


def problem_folder_payload(metadata: dict[str, Any], problem_dir: Path) -> dict[str, Any]:
    """Return folder fields used by the web problem list."""
    folder = metadata.get("folder")
    return {
        "folder": folder if isinstance(folder, str) else "",
        "folderEditable": problem_folder_editable(problem_dir),
    }


def update_problem_folder(problem_id: str, folder: str | None) -> dict[str, Any]:
    """Update the display folder in a problem metadata file."""
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
