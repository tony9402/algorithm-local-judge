"""editor 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from judge.core.compiler import SUPPORTED_USER_SUFFIXES
from judge.core.errors import JudgeError
from judge.core.paths import ensure_inside, rel
from judge.core.problem_constants import REQUIRED_TOOL_FIELDS
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
    "cpp": ("#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    return 0;\n}\n"),
    "python": (
        'import sys\n\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n'
    ),
    "java": "class Main {\n    public static void main(String[] args) {\n    }\n}\n",
}
METADATA_TIMEOUT_FIELDS = {
    "compileTimeoutMs",
    "generationTimeoutMs",
    "solutionTimeoutMs",
    "userTimeoutMs",
}


def safe_problem_file(workspace: Path, problem_id: str, raw_path: str) -> Path:
    """safe_problem_file 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        raw_path (str): `raw_path` 값입니다.
    
    Returns:
        Path: 처리 결과를 반환합니다.
    """
    if not raw_path or raw_path.startswith("/"):
        raise JudgeError(f"invalid problem file path: {raw_path}")
    relative = Path(raw_path)
    if ".." in relative.parts:
        raise JudgeError(f"invalid problem file path: {raw_path}")
    base = problem_dir(workspace, problem_id)
    return ensure_inside(base / relative, base)


def list_problem_files(workspace: Path, problem_id: str) -> list[dict[str, Any]]:
    """list_problem_files 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
    
    Returns:
        list[dict[str, Any]]: 처리 결과를 반환합니다.
    """
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
    """read_problem_file 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        raw_path (str): `raw_path` 값입니다.
    
    Returns:
        dict[str, str]: 처리 결과를 반환합니다.
    """
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
    """write_problem_file 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        raw_path (str): `raw_path` 값입니다.
        content (str): 요청/저장할 내용입니다.
    
    Returns:
        dict[str, str]: 처리 결과를 반환합니다.
    """
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
    """save_solution_upload 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        filename (str): `filename` 값입니다.
        content (bytes): 요청/저장할 내용입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
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
    """safe_solution_base_name 함수를 실행하고 결과를 반환합니다.
    
    Args:
        value (str): 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
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
    """create_solution_file 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        name (str): 이름입니다.
        expected (str): `expected` 값입니다.
        language (str): `language` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
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
    """rename_solution_file 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        raw_path (str): `raw_path` 값입니다.
        name (str): 이름입니다.
        expected (str): `expected` 값입니다.
        language (str): `language` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
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


def validate_metadata_relative_path(label: str, value: Any) -> None:
    """validate_metadata_relative_path 함수를 실행하고 결과를 반환합니다.
    
    Args:
        label (str): `label` 값입니다.
        value (Any): 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    if not isinstance(value, str):
        raise JudgeError(f"{label} path must be a string")
    normalized = value.replace("\\", "/").strip()
    if not normalized or normalized == ".":
        raise JudgeError(f"{label} path must be a non-empty relative path")
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise JudgeError(f"unsafe {label} path in metadata: {value}")


def validate_problem_metadata_patch(metadata: dict[str, Any]) -> None:
    """validate_problem_metadata_patch 함수를 실행하고 결과를 반환합니다.
    
    Args:
        metadata (dict[str, Any]): `metadata` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    tools = metadata.get("tools")
    if tools is not None:
        if not isinstance(tools, dict):
            raise JudgeError("metadata tools must be an object")
        missing = [name for name in REQUIRED_TOOL_FIELDS if name not in tools]
        if missing:
            raise JudgeError(f"missing tool path(s): {', '.join(missing)}")
        for name in REQUIRED_TOOL_FIELDS:
            validate_metadata_relative_path(name, tools[name])

    limits = metadata.get("limits")
    if limits is not None:
        if not isinstance(limits, dict):
            raise JudgeError("metadata limits must be an object")
        for name, value in limits.items():
            if name in METADATA_TIMEOUT_FIELDS and (
                not isinstance(value, int) or isinstance(value, bool) or value < 1
            ):
                raise JudgeError(f"{name} must be a positive integer")


def update_problem_metadata(
    workspace: Path, problem_id: str, metadata_patch: dict[str, Any]
) -> dict[str, Any]:
    """update_problem_metadata 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        metadata_patch (dict[str, Any]): `metadata_patch` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    path = safe_problem_file(workspace, problem_id, "problem.json")
    metadata = read_json(path)
    metadata.update(metadata_patch)
    metadata["problemId"] = problem_id
    validate_problem_metadata_patch(metadata)
    write_json(path, metadata)
    return metadata
