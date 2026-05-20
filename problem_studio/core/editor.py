from __future__ import annotations

from pathlib import Path
from typing import Any

from judge.core.compiler import SUPPORTED_USER_SUFFIXES
from judge.core.errors import JudgeError
from judge.core.paths import ensure_inside, rel
from judge.utils.fs import read_json, write_json
from problem_studio.core.workspace import problem_dir

SAFE_UPLOAD_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
SOLUTION_EXPECTED_TOKENS = {"ac", "wa", "tle", "mle"}
SOLUTION_LANGUAGE_EXTENSIONS = {
    "cpp": ".cpp",
    "python": ".py",
    "java": ".java",
}
SOLUTION_TEMPLATES = {
    "cpp": (
        "#include <bits/stdc++.h>\n"
        "using namespace std;\n\n"
        "int main() {\n"
        "    return 0;\n"
        "}\n"
    ),
    "python": (
        "import sys\n\n\n"
        "def main():\n"
        "    pass\n\n\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    ),
    "java": "class Main {\n    public static void main(String[] args) {\n    }\n}\n",
}


def safe_problem_file(workspace: Path, problem_id: str, raw_path: str) -> Path:
    """Return a validated file path inside one problem directory."""
    if not raw_path or raw_path.startswith("/"):
        raise JudgeError(f"invalid problem file path: {raw_path}")
    relative = Path(raw_path)
    if ".." in relative.parts:
        raise JudgeError(f"invalid problem file path: {raw_path}")
    base = problem_dir(workspace, problem_id)
    return ensure_inside(base / relative, base)


def list_problem_files(workspace: Path, problem_id: str) -> list[dict[str, Any]]:
    """Return editable files under one problem directory."""
    base = problem_dir(workspace, problem_id)
    if not base.exists():
        raise JudgeError(f"problem not found: {problem_id}")
    files = []
    for path in sorted(item for item in base.rglob("*") if item.is_file()):
        relative = path.relative_to(base).as_posix()
        if "__pycache__" in path.parts:
            continue
        files.append({"path": relative, "size": path.stat().st_size})
    return files


def read_problem_file(workspace: Path, problem_id: str, raw_path: str) -> dict[str, str]:
    """Read a UTF-8 problem file for editing."""
    path = safe_problem_file(workspace, problem_id, raw_path)
    if not path.exists():
        raise JudgeError(f"problem file not found: {rel(path, workspace)}")
    return {
        "path": raw_path,
        "content": path.read_text(encoding="utf-8", errors="replace"),
    }


def write_problem_file(
    workspace: Path, problem_id: str, raw_path: str, content: str
) -> dict[str, str]:
    """Write a UTF-8 problem file after validating it stays inside the problem."""
    path = safe_problem_file(workspace, problem_id, raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": raw_path, "label": rel(path, workspace)}


def save_solution_upload(
    workspace: Path,
    problem_id: str,
    filename: str,
    content: bytes,
) -> dict[str, Any]:
    """Save one uploaded expected-result solution under the problem solutions directory."""
    name = Path(filename).name
    if not name or any(char not in SAFE_UPLOAD_NAME_CHARS for char in name):
        raise JudgeError(f"invalid solution filename: {filename}")
    if Path(name).suffix.lower() not in SUPPORTED_USER_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_USER_SUFFIXES))
        raise JudgeError(
            f"unsupported solution extension: {Path(name).suffix} (supported: {supported})"
        )
    path = safe_problem_file(workspace, problem_id, f"solutions/{name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"path": f"solutions/{name}", "size": path.stat().st_size}


def safe_solution_base_name(value: str) -> str:
    """Return a safe solution base name without result token or extension."""
    name = value.strip().replace(" ", "_")
    if not name or any(char not in SAFE_UPLOAD_NAME_CHARS for char in name):
        raise JudgeError(f"invalid solution name: {value}")
    while Path(name).suffix:
        name = Path(name).stem
    if not name:
        raise JudgeError(f"invalid solution name: {value}")
    return name


def create_solution_file(
    workspace: Path,
    problem_id: str,
    name: str,
    expected: str,
    language: str,
) -> dict[str, Any]:
    """Create a new empty expected-result solution file."""
    if expected not in SOLUTION_EXPECTED_TOKENS:
        raise JudgeError(f"unknown expected result token: {expected}")
    if language not in SOLUTION_LANGUAGE_EXTENSIONS:
        raise JudgeError(f"unknown solution language: {language}")
    base_name = safe_solution_base_name(name)
    filename = f"{base_name}.{expected}{SOLUTION_LANGUAGE_EXTENSIONS[language]}"
    path = safe_problem_file(workspace, problem_id, f"solutions/{filename}")
    if path.exists():
        raise JudgeError(f"solution already exists: {filename}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SOLUTION_TEMPLATES[language], encoding="utf-8")
    return {"path": f"solutions/{filename}", "size": path.stat().st_size}


def rename_solution_file(
    workspace: Path,
    problem_id: str,
    raw_path: str,
    name: str,
    expected: str,
    language: str,
) -> dict[str, Any]:
    """Rename an existing expected-result solution file and keep metadata in sync."""
    if not raw_path.startswith("solutions/"):
        raise JudgeError(f"not a solution file: {raw_path}")
    if expected not in SOLUTION_EXPECTED_TOKENS:
        raise JudgeError(f"unknown expected result token: {expected}")
    if language not in SOLUTION_LANGUAGE_EXTENSIONS:
        raise JudgeError(f"unknown solution language: {language}")

    old_path = safe_problem_file(workspace, problem_id, raw_path)
    if not old_path.exists():
        raise JudgeError(f"solution file not found: {raw_path}")

    base_name = safe_solution_base_name(name)
    filename = f"{base_name}.{expected}{SOLUTION_LANGUAGE_EXTENSIONS[language]}"
    new_raw_path = f"solutions/{filename}"
    new_path = safe_problem_file(workspace, problem_id, new_raw_path)
    if new_path != old_path and new_path.exists():
        raise JudgeError(f"solution already exists: {filename}")

    if new_path != old_path:
        old_path.replace(new_path)

    metadata_path = safe_problem_file(workspace, problem_id, "problem.json")
    metadata = read_json(metadata_path)
    tools = metadata.setdefault("tools", {})
    if tools.get("solution") == raw_path:
        tools["solution"] = new_raw_path
        write_json(metadata_path, metadata)

    return {
        "path": new_raw_path,
        "size": new_path.stat().st_size,
        "metadata": metadata,
    }


def update_problem_metadata(
    workspace: Path, problem_id: str, metadata_patch: dict[str, Any]
) -> dict[str, Any]:
    """Merge and write problem.json metadata for a problem."""
    path = safe_problem_file(workspace, problem_id, "problem.json")
    metadata = read_json(path)
    metadata.update(metadata_patch)
    metadata["problemId"] = problem_id
    write_json(path, metadata)
    return metadata
