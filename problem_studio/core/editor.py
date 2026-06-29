"""편집기 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from alj_core.compiler import SUPPORTED_USER_SUFFIXES
from alj_core.errors import JudgeError
from alj_core.paths import ensure_inside, rel
from alj_core.problem_constants import REQUIRED_TOOL_FIELDS
from alj_core.utils.fs import read_json, write_json
from problem_studio.core.workspace import problem_dir

SAFE_UPLOAD_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
SOLUTION_EXPECTED_TOKENS = {"ac", "wa", "tle", "mle"}
SOLUTION_LANGUAGE_EXTENSIONS = {
    "cpp": ".cpp",
    "python": ".py",
    "pypy": ".py",
    "java": ".java",
}
SOLUTION_LANGUAGE_MARKERS = {
    "pypy": ".pypy",
}
SOLUTION_TEMPLATES = {
    "cpp": ("#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    return 0;\n}\n"),
    "python": (
        'import sys\n\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n'
    ),
    "pypy": (
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
METADATA_MEMORY_FIELDS = {
    "userMemoryLimitBytes",
    "memoryLimitBytes",
    "userMemoryLimitMb",
    "memoryLimitMb",
}


def safe_problem_file(workspace: Path, problem_id: str, raw_path: str) -> Path:
    if not raw_path or raw_path.startswith("/"):
        raise JudgeError(f"invalid problem file path: {raw_path}")
    relative = Path(raw_path)
    if ".." in relative.parts:
        raise JudgeError(f"invalid problem file path: {raw_path}")
    base = problem_dir(workspace, problem_id)
    return ensure_inside(base / relative, base)


def list_problem_files(workspace: Path, problem_id: str) -> list[dict[str, Any]]:
    """현재 설정과 파일시스템을 기준으로 문제 파일 목록을 조회합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.

    Returns:
        list[dict[str, Any]]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 파일 데이터입니다.
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
    """문제 파일 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        raw_path (str): raw 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.

    Returns:
        dict[str, str]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 파일 데이터입니다.
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
    """문제 파일 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        raw_path (str): raw 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        content (str): 파일이나 편집기 버퍼에 저장할 본문입니다.

    Returns:
        dict[str, str]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 파일 데이터입니다.
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
    """솔루션 업로드 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        filename (str): 업로드 또는 직접 입력 소스에 붙일 파일 이름입니다.
        content (bytes): 파일이나 편집기 버퍼에 저장할 본문입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 업로드 데이터입니다.
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
    name = value.strip().replace(" ", "_")
    if not name or any(char not in SAFE_UPLOAD_NAME_CHARS for char in name):
        raise JudgeError(f"invalid solution name: {value}")
    while Path(name).suffix:
        name = Path(name).stem
    if not name:
        raise JudgeError(f"invalid solution name: {value}")
    return name


def solution_filename(base_name: str, expected: str, language: str) -> str:
    marker = SOLUTION_LANGUAGE_MARKERS.get(language, "")
    return f"{base_name}{marker}.{expected}{SOLUTION_LANGUAGE_EXTENSIONS[language]}"


def create_solution_file(
    workspace: Path,
    problem_id: str,
    name: str,
    expected: str,
    language: str,
) -> dict[str, Any]:
    """솔루션 파일 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        name (str): 사용자 표시와 내부 조회에 함께 쓰는 항목 이름입니다.
        expected (str): 솔루션 파일을 계산하거나 검증할 때 필요한 기대 입력입니다.
        language (str): 솔루션 파일을 계산하거나 검증할 때 필요한 language 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 솔루션 파일 데이터입니다.
    """
    if expected not in SOLUTION_EXPECTED_TOKENS:
        raise JudgeError(f"unknown expected result token: {expected}")
    if language not in SOLUTION_LANGUAGE_EXTENSIONS:
        raise JudgeError(f"unknown solution language: {language}")
    base_name = safe_solution_base_name(name)
    filename = solution_filename(base_name, expected, language)
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
    filename = solution_filename(base_name, expected, language)
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


def _fallback_reference_solution(base: Path, deleted_raw_path: str) -> str | None:
    solutions_dir = base / "solutions"
    if not solutions_dir.exists():
        return None
    for source in sorted(path for path in solutions_dir.rglob("*") if path.is_file()):
        relative = source.relative_to(base).as_posix()
        if relative == deleted_raw_path:
            continue
        if source.suffix.lower() not in SUPPORTED_USER_SUFFIXES:
            continue
        parts = source.name.split(".")
        if len(parts) >= 3 and parts[-2].lower() == "ac":
            return relative
    return None


def delete_solution_file(workspace: Path, problem_id: str, raw_path: str) -> dict[str, Any]:
    """솔루션 파일을 삭제하고 참조 정답 메타데이터를 안전하게 유지합니다."""
    if not raw_path.startswith("solutions/"):
        raise JudgeError(f"not a solution file: {raw_path}")

    path = safe_problem_file(workspace, problem_id, raw_path)
    if not path.exists() or not path.is_file():
        raise JudgeError(f"solution file not found: {raw_path}")

    metadata_path = safe_problem_file(workspace, problem_id, "problem.json")
    metadata = read_json(metadata_path)
    tools = metadata.setdefault("tools", {})
    reference_deleted = tools.get("solution") == raw_path
    if reference_deleted:
        fallback = _fallback_reference_solution(problem_dir(workspace, problem_id), raw_path)
        if not fallback:
            raise JudgeError(
                "cannot delete reference solution without another accepted solution"
            )
        tools["solution"] = fallback

    path.unlink()
    if reference_deleted:
        write_json(metadata_path, metadata)

    return {
        "deleted": {"path": raw_path},
        "metadata": metadata,
        "referenceChanged": reference_deleted,
    }


def validate_metadata_relative_path(label: str, value: Any) -> None:
    """메타데이터 relative 경로 값이 허용되는 형식과 정책을 만족하는지 검사합니다.

    Args:
        label (str): 진단 결과나 UI 항목에서 사람이 읽을 수 있게 표시할 이름입니다.
        value (Any): 검증하거나 상태에 반영할 입력 값입니다.
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
    """문제 메타데이터 patch 값이 허용되는 형식과 정책을 만족하는지 검사합니다.

    Args:
        metadata (dict[str, Any]): 문제, 소스, 실행 결과에 붙는 제목, 제한, 경로 같은 부가 정보입니다.
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
            if name in METADATA_MEMORY_FIELDS and (
                not isinstance(value, int) or isinstance(value, bool) or value < 1
            ):
                raise JudgeError(f"{name} must be a positive integer")


def update_problem_metadata(
    workspace: Path, problem_id: str, metadata_patch: dict[str, Any]
) -> dict[str, Any]:
    """문제 메타데이터 상태를 새 입력에 맞춰 갱신하고 필요한 후속 표시를 조정합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        metadata_patch (dict[str, Any]): 문제 메타데이터을 계산하거나 검증할 때 필요한 메타데이터 patch 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 메타데이터 데이터입니다.
    """
    path = safe_problem_file(workspace, problem_id, "problem.json")
    metadata = read_json(path)
    metadata.update(metadata_patch)
    metadata["problemId"] = problem_id
    validate_problem_metadata_patch(metadata)
    write_json(path, metadata)
    return metadata
